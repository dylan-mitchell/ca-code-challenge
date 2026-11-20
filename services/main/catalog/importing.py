"""Create-only WordPress content import. Auth writes and identities stay external."""
import json
import os
import re
from datetime import datetime, timezone
from uuid import UUID

import pymysql
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import transaction

from .content import sanitize_html, short_description
from .models import Brand, Industry, Review, Reviewer


def load_identity_map(path):
    try:
        with open(path, encoding="utf-8") as stream:
            raw = json.load(stream)
        if not isinstance(raw, dict):
            raise ValueError("Expected a WordPress ID to UUID object.")
        result = {}
        for key, value in raw.items():
            if not re.fullmatch(r"[1-9][0-9]*", key) or not isinstance(value, str):
                raise ValueError("Invalid identity mapping entry.")
            result[int(key)] = UUID(value)
        if len(set(result.values())) != len(result):
            raise ValueError("Different WordPress users cannot share an auth UUID.")
        return result
    except (OSError, ValueError, TypeError) as exc:
        raise CommandError(f"Cannot read auth identity mapping: {exc}") from exc


def read_source():
    connection = pymysql.connect(
        host=os.environ.get("SOURCE_DB_HOST", "source-db"),
        port=int(os.environ.get("SOURCE_DB_PORT", "3306")),
        user=os.environ.get("SOURCE_DB_USER", "import_reader"),
        password=os.environ.get("SOURCE_DB_PASSWORD", ""),
        database=os.environ.get("SOURCE_DB_NAME", "wp"), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, connect_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute("""
                SELECT ID, post_author, post_date_gmt, post_content, post_title,
                       post_excerpt, post_name, post_type
                FROM wp_posts WHERE post_status = 'publish'
                AND post_type IN ('brand', 'review') ORDER BY ID
            """)
            posts = cursor.fetchall()
            cursor.execute("""
                SELECT DISTINCT t.term_id, t.name, t.slug FROM wp_terms t
                JOIN wp_term_taxonomy tt ON tt.term_id = t.term_id
                WHERE tt.taxonomy = 'industry' ORDER BY t.term_id
            """)
            industries = cursor.fetchall()
            cursor.execute("""
                SELECT u.ID, u.display_name FROM wp_users u
                WHERE EXISTS (SELECT 1 FROM wp_posts p WHERE p.post_author = u.ID
                    AND p.post_type = 'review' AND p.post_status = 'publish') ORDER BY u.ID
            """)
            users = cursor.fetchall()
            cursor.execute("""
                SELECT m.post_id, m.meta_key, m.meta_value FROM wp_postmeta m
                JOIN wp_posts p ON p.ID = m.post_id
                WHERE p.post_status = 'publish' AND p.post_type IN ('brand', 'review')
                AND m.meta_key IN ('website_url','founded_year','headquarters','rating','brand','reviewer_name','reviewer_location')
                ORDER BY m.meta_id
            """)
            metadata = {}
            for row in cursor.fetchall():
                fields = metadata.setdefault(row["post_id"], {})
                if row["meta_key"] in fields:
                    raise CommandError(f"Post {row['post_id']}: duplicate metadata field {row['meta_key']}.")
                fields[row["meta_key"]] = row["meta_value"]
            cursor.execute("""
                SELECT tr.object_id, tt.term_id FROM wp_term_relationships tr
                JOIN wp_term_taxonomy tt ON tt.term_taxonomy_id = tr.term_taxonomy_id
                JOIN wp_posts p ON p.ID = tr.object_id
                WHERE tt.taxonomy = 'industry' AND p.post_type = 'brand' AND p.post_status = 'publish'
                ORDER BY tr.object_id, tt.term_id
            """)
            links = {}
            for row in cursor.fetchall():
                links.setdefault(row["object_id"], []).append(row["term_id"])
        return {"posts": posts, "industries": industries, "users": users, "metadata": metadata, "links": links}
    finally:
        connection.rollback()
        connection.close()


def _integer(value, entity, field, optional=False):
    if optional and (value is None or value == ""):
        return None
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value or "")):
        raise CommandError(f"{entity}: {field} must be a whole number.")
    return int(value)


def _publication(value, entity):
    try:
        date = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise CommandError(f"{entity}: post_date_gmt must be a valid original publication timestamp.") from None


def _create(model, wordpress_id, **values):
    record = model(wordpress_id=wordpress_id, **values)
    try:
        record.full_clean()
        record.save()
    except ValidationError as exc:
        raise CommandError(f"{model.__name__} WordPress ID {wordpress_id}: {exc.message_dict}") from exc
    return record


@transaction.atomic
def import_content(source, identities):
    counts = {name: {"created": 0, "existing": 0} for name in ("industries", "reviewers", "brands", "reviews")}

    def count(name, created):
        counts[name]["created" if created else "existing"] += 1

    industries = {}
    for row in source["industries"]:
        record = Industry.objects.filter(wordpress_id=row["term_id"]).first()
        count("industries", record is None)
        if record is None:
            record = _create(Industry, row["term_id"], name=row["name"], slug=row["slug"])
        industries[row["term_id"]] = record

    reviewers = {}
    for row in source["users"]:
        user_id = row["ID"]
        if user_id not in identities:
            raise CommandError(f"Reviewer WordPress ID {user_id}: missing auth UUID mapping.")
        record = Reviewer.objects.filter(wordpress_id=user_id).first()
        count("reviewers", record is None)
        if record is None:
            record = _create(Reviewer, user_id, auth_user_id=identities[user_id], display_name=row["display_name"])
        elif record.auth_user_id != identities[user_id]:
            raise CommandError(f"Reviewer WordPress ID {user_id}: auth UUID conflicts with the existing profile.")
        reviewers[user_id] = record

    brands = {}
    for row in source["posts"]:
        if row["post_type"] != "brand":
            continue
        source_id = row["ID"]
        record = Brand.objects.filter(wordpress_id=source_id).first()
        count("brands", record is None)
        if record is None:
            metadata = source["metadata"].get(source_id, {})
            record = _create(
                Brand, source_id, name=row["post_title"], slug=row["post_name"],
                description_html=sanitize_html(row["post_content"]),
                short_description=short_description(row["post_excerpt"], row["post_content"]),
                website_url=metadata.get("website_url", ""), headquarters=metadata.get("headquarters", ""),
                founded_year=_integer(metadata.get("founded_year"), f"Brand WordPress ID {source_id}", "founded_year", optional=True),
            )
            try:
                record.industries.set([industries[item] for item in source["links"].get(source_id, [])])
            except KeyError as exc:
                raise CommandError(f"Brand WordPress ID {source_id}: unknown industry {exc.args[0]}.") from exc
        brands[source_id] = record

    for row in source["posts"]:
        if row["post_type"] != "review":
            continue
        source_id = row["ID"]
        record = Review.objects.filter(wordpress_id=source_id).first()
        count("reviews", record is None)
        if record is not None:
            continue
        entity = f"Review WordPress ID {source_id}"
        metadata = source["metadata"].get(source_id, {})
        brand_id = _integer(metadata.get("brand"), entity, "brand")
        if brand_id not in brands:
            raise CommandError(f"{entity}: unknown published brand {brand_id}.")
        if row["post_author"] not in reviewers:
            raise CommandError(f"{entity}: unknown reviewer {row['post_author']}.")
        _create(
            Review, source_id, brand=brands[brand_id], reviewer=reviewers[row["post_author"]],
            title=row["post_title"], slug=row["post_name"], body_html=sanitize_html(row["post_content"]),
            rating=_integer(metadata.get("rating"), entity, "rating"), published_at=_publication(row["post_date_gmt"], entity),
            reviewer_name=metadata.get("reviewer_name", ""), reviewer_location=metadata.get("reviewer_location", ""),
        )
    return counts

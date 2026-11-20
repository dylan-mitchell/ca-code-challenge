"""Read only the WordPress account data required by this service."""

import os
import re
from datetime import datetime, timezone

import pymysql
from django.core.management.base import CommandError
from review_auth import Role


def read_source_users() -> list[dict]:
    try:
        connection = pymysql.connect(
            host=os.environ.get("SOURCE_DB_HOST", "source-db"),
            port=int(os.environ.get("SOURCE_DB_PORT", "3306")),
            database=os.environ.get("SOURCE_DB_NAME", "wp"),
            user=os.environ.get("SOURCE_DB_USER", "wp_reader"),
            password=os.environ.get("SOURCE_DB_PASSWORD", ""),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                connection.begin()
                cursor.execute(
                    """
                    SELECT u.ID AS wordpress_id, u.user_login AS username,
                           u.user_email AS email, u.user_registered AS registered_at,
                           m.meta_value AS capabilities
                    FROM wp_users u
                    LEFT JOIN wp_usermeta m ON m.user_id = u.ID
                         AND m.meta_key = 'wp_capabilities'
                    ORDER BY u.ID
                    """
                )
                return list(cursor.fetchall())
        finally:
            connection.close()
    except (pymysql.MySQLError, ValueError) as exc:
        raise CommandError("Could not read accounts from the WordPress source database.") from exc


def parse_capabilities(serialized: str) -> dict[str, bool]:
    """Parse WP's flat serialized string→boolean map, never executable PHP.

    String lengths in PHP serialization count bytes, not Unicode characters.
    Reject objects, nested structures, duplicate keys and trailing input.
    """
    if not isinstance(serialized, str):
        raise ValueError("Expected a serialized WordPress capability map.")
    data = serialized.encode("utf-8")
    header = re.match(rb"a:([0-9]+):\{", data)
    if header is None:
        raise ValueError("Expected a serialized WordPress capability map.")
    count = int(header[1])
    position = header.end()
    capabilities = {}
    for _ in range(count):
        key = re.match(rb's:([0-9]+):"', data[position:])
        if key is None:
            raise ValueError("Malformed WordPress capability key.")
        position += key.end()
        end = position + int(key[1])
        try:
            name = data[position:end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Malformed WordPress capability name.") from exc
        position = end
        value = re.match(rb'";b:([01]);', data[position:])
        if value is None or name in capabilities:
            raise ValueError("Malformed or duplicate WordPress capability.")
        capabilities[name] = value[1] == b"1"
        position += value.end()
    if data[position:] != b"}":
        raise ValueError("Malformed WordPress capability map ending.")
    return capabilities


def imported_role(capabilities: str) -> str:
    roles = parse_capabilities(capabilities)
    if roles.get("administrator"):
        return Role.EDITOR.value
    if roles.get("subscriber"):
        return Role.READER.value
    raise ValueError("Expected the subscriber or administrator WordPress role.")


def registration_timestamp(value) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("Expected a valid WordPress registration timestamp.")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

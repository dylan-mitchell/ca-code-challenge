import json
import os
import tempfile
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from accounts.models import User
from accounts.wordpress import imported_role, read_source_users, registration_timestamp


def publish_mapping(path: Path, mapping: dict[str, str]) -> None:
    """Publish a complete file after commit, never a partially written map."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(mapping, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Command(BaseCommand):
    help = "Create missing WordPress accounts and export their auth public UUIDs."

    def add_arguments(self, parser):
        parser.add_argument("--mapping-output", type=Path, required=True)

    def handle(self, *args, **options):
        rows = read_source_users()
        source_ids = [row["wordpress_id"] for row in rows]
        if any(type(identifier) is not int or identifier <= 0 for identifier in source_ids):
            raise CommandError("WordPress user: wordpress_id must be a positive integer.")
        if len(set(source_ids)) != len(source_ids):
            raise CommandError("WordPress user: duplicate IDs or capability records in the source.")

        mapping = {}
        created = 0
        reused = 0
        try:
            with transaction.atomic():
                existing = {
                    user.wordpress_id: user
                    for user in User.objects.filter(wordpress_id__in=source_ids)
                }
                for row in rows:
                    source_id = row["wordpress_id"]
                    user = existing.get(source_id)
                    if user is not None:
                        reused += 1
                    else:
                        user = self.create_user(row)
                        created += 1
                    mapping[str(source_id)] = str(user.public_id)
        except CommandError as exc:
            raise CommandError(f"Auth import rolled back. {exc}") from exc
        except DatabaseError as exc:
            raise CommandError(
                "Auth import rolled back because a database constraint or operation failed."
            ) from exc

        self.stdout.write(f"Auth import committed: created={created}, existing={reused}.")
        try:
            publish_mapping(Path(options["mapping_output"]), mapping)
        except OSError as exc:
            raise CommandError(
                "Auth accounts were committed, but identity mapping export failed. "
                "Do not run the content import; rerun to regenerate the mapping."
            ) from exc
        self.stdout.write(f"Published {len(mapping)} account identities.")

    def create_user(self, row):
        source_id = row["wordpress_id"]
        password = os.environ.get("AUTH_IMPORT_PASSWORD", "")
        if not password:
            raise CommandError(
                f"WordPress user {source_id}: configure AUTH_IMPORT_PASSWORD "
                "before creating new accounts."
            )
        username = row["username"]
        if not isinstance(username, str) or not username.strip():
            raise CommandError(f"WordPress user {source_id}: username must not be blank.")
        if User.objects.filter(username=username).exists():
            raise CommandError(
                f"WordPress user {source_id}: username conflicts with a different account."
            )
        try:
            role = imported_role(row["capabilities"])
        except ValueError as exc:
            raise CommandError(f"WordPress user {source_id}: role: {exc}") from exc
        try:
            joined = registration_timestamp(row["registered_at"])
        except ValueError as exc:
            raise CommandError(f"WordPress user {source_id}: date_joined: {exc}") from exc
        user = User(
            wordpress_id=source_id,
            username=username,
            email=row["email"],
            role=role,
            date_joined=joined,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        user.set_password(password)
        try:
            user.full_clean()
        except ValidationError as exc:
            details = "; ".join(
                f"{field}: {', '.join(messages)}"
                for field, messages in exc.message_dict.items()
            )
            raise CommandError(f"WordPress user {source_id}: {details}") from exc
        user.save()
        return user

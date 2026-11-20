import json

import pymysql
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from catalog.importing import import_content, load_identity_map, read_source


class Command(BaseCommand):
    help = "Create missing WordPress content using committed auth identity mappings."

    def add_arguments(self, parser):
        parser.add_argument("--auth-map", required=True, help="JSON map emitted after the auth import commits.")

    def handle(self, *args, **options):
        identities = load_identity_map(options["auth_map"])
        try:
            source = read_source()
            result = import_content(source, identities)
        except (pymysql.MySQLError, DatabaseError, CommandError) as exc:
            raise CommandError(f"Content import failed; destination phase was not committed: {exc}") from exc
        self.stdout.write(json.dumps(result, sort_keys=True))

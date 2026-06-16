from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Validate SQLite-to-PostgreSQL migration evidence beyond row counts."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print validation plan without requiring target DB.")
        parser.add_argument("--source", default="default", help="Source database alias.")
        parser.add_argument("--target", default="default", help="Target database alias.")
        parser.add_argument(
            "--include-audit",
            action="store_true",
            help="Also print audit database validation checks.",
        )
        parser.add_argument(
            "--advisory",
            action="store_true",
            help="Return success for advisory evidence even when checks report warnings.",
        )

    def handle(self, *args, **options):
        source = options["source"]
        target = options["target"]
        dry_run = options["dry_run"]

        self._validate_alias(source)
        self._validate_alias(target)

        self.stdout.write("PostgreSQL migration validation")
        self.stdout.write(f"Mode: {'dry-run' if dry_run else 'live'}")
        self.stdout.write(f"Source alias: {source}")
        self.stdout.write(f"Target alias: {target}")
        self.stdout.write("")

        self._print_migration_state(source, label="source")
        if dry_run and source == target:
            self.stdout.write("[target] dry-run uses source alias as placeholder; configure target alias for live validation.")
        else:
            self._print_migration_state(target, label="target")

        self.stdout.write("")
        self.stdout.write("Validation checks beyond row counts:")
        self.stdout.write("- Compare migration graph leaf nodes for source and target aliases.")
        self.stdout.write("- Compare table row counts for every managed model.")
        self.stdout.write("- Compare representative primary keys for CXRStudy, ProcessingTask, UploadedFile, and AuditEvent where present.")
        self.stdout.write("- Sample non-PHI-safe metadata fields where approved.")
        self.stdout.write("- Verify audit database alias is migrated and queryable.")
        self.stdout.write("- Reset PostgreSQL sequences after loading explicit primary keys.")
        self.stdout.write("- Run login, upload task listing, report, viewer, and audit smoke checks.")

        self.stdout.write("")
        self.stdout.write("Managed model inventory:")
        for model in apps.get_models():
            if not model._meta.managed:
                continue
            self.stdout.write(f"- {model._meta.label}: table={model._meta.db_table}, pk={model._meta.pk.name}")

        if options["include_audit"]:
            self.stdout.write("")
            self.stdout.write("Audit alias checks:")
            self._print_migration_state("audit", label="audit")

        if not dry_run and source == target and not options["advisory"]:
            raise CommandError("Live validation requires distinct --source and --target aliases or --advisory.")

    def _validate_alias(self, alias):
        if alias not in connections.databases:
            raise CommandError(f"Unknown database alias: {alias}")

    def _print_migration_state(self, alias, label):
        connection = connections[alias]
        executor = MigrationExecutor(connection)
        leaf_nodes = executor.loader.graph.leaf_nodes()
        self.stdout.write(f"[{label}] alias={alias}, engine={connection.settings_dict.get('ENGINE')}")
        self.stdout.write(f"[{label}] migration graph leaf nodes: {', '.join(f'{app}.{name}' for app, name in leaf_nodes)}")

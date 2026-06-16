from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Prepare an operator-controlled SQLite-to-PostgreSQL migration checklist."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print checklist without writing artifacts.")
        parser.add_argument(
            "--allow-export",
            action="store_true",
            help="Acknowledge operator approval to write export command guidance.",
        )
        parser.add_argument(
            "--output-dir",
            default="migration_artifacts",
            help="Directory for operator-approved migration artifacts.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        allow_export = options["allow_export"]
        output_dir = Path(options["output_dir"])

        if not dry_run and not allow_export:
            raise CommandError(
                "Refusing to prepare export artifacts without --allow-export. "
                "Use --dry-run for checklist-only output."
            )

        aliases = ("default", "audit")
        self.stdout.write("SQLite-to-PostgreSQL migration preparation")
        self.stdout.write(f"Mode: {'dry-run' if dry_run else 'operator-approved export preparation'}")
        self.stdout.write(f"Output directory: {output_dir}")
        self.stdout.write("")

        for alias in aliases:
            config = connections.databases[alias]
            self.stdout.write(f"[{alias}]")
            self.stdout.write(f"  engine: {config.get('ENGINE')}")
            self.stdout.write(f"  name: {config.get('NAME')}")
            self.stdout.write(f"  migrated apps: {', '.join(self._app_labels_for_alias(alias))}")
            self.stdout.write(
                "  export command: "
                f"python django-app\\manage.py dumpdata --database {alias} "
                "--natural-foreign --natural-primary --indent 2 "
                f"-o {output_dir / (alias + '-sqlite-export.json')}"
            )
            self.stdout.write(
                "  import command: "
                f"python django-app\\manage.py loaddata {output_dir / (alias + '-sqlite-export.json')} "
                f"--database {alias}"
            )
            self.stdout.write("")

        self.stdout.write("Required operator controls:")
        self.stdout.write("- Back up SQLite files before export.")
        self.stdout.write("- Rehearse with synthetic or explicitly approved non-PHI data.")
        self.stdout.write("- Run migrations on PostgreSQL before loading fixtures.")
        self.stdout.write("- Run validate_postgres_migration after import.")
        self.stdout.write("- Do not perform production cutover from this command alone.")

    def _app_labels_for_alias(self, alias):
        labels = []
        for app_config in settings.INSTALLED_APPS:
            label = app_config.rsplit(".", 2)[0].split(".")[-1] if app_config.endswith("Config") else app_config.split(".")[-1]
            if alias == "audit" and label != "audit":
                continue
            if alias == "default" and label == "audit":
                continue
            labels.append(label)
        return labels

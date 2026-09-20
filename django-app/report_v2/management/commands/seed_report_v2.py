# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""``manage.py seed_report_v2`` -- load the reviewed report-v2 seed as admin-editable drafts only.

The command is a thin driver over the pure :mod:`report_v2.seeding` engine. It resolves the target root,
runs the full validation battery, and only then installs the seed pair as drafts. It never publishes, never
touches the database, and never sends email; the engine owns every write and exposes no publication path.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from report_v2 import seeding
from report_v2.definitions.repository import default_root, RepositoryError, validate_definition_id


class Command(BaseCommand):
    help = "Validate and load the reviewed report-v2 seed into admin-editable DRAFTS (never publishes)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--def-id",
            default=seeding.SEED_DEF_ID,
            help="Definition id to install the report draft under (the policy draft takes this id plus the policy suffix).",
        )
        parser.add_argument(
            "--root",
            default=None,
            help="Definition repository root (defaults to the configured report-v2 private root).",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Validate and report only; write nothing.",
        )

    def handle(self, *args, **options):
        def_id = options["def_id"]
        try:
            validate_definition_id(def_id)
            validate_definition_id(f"{def_id}{seeding.POLICY_SUFFIX}")
        except RepositoryError as exc:
            raise CommandError(str(exc)) from exc
        root_arg = options.get("root")
        root = Path(root_arg) if root_arg else default_root()

        violations = list(seeding.validate_seeds()) + list(seeding.validate_seed_bindings())
        for violation in violations:
            self.stderr.write(f"{violation}\n")
        if violations:
            raise SystemExit(1)

        if options.get("check"):
            summary = seeding.seed_summary()
            self.stdout.write(f"SEED-CHECK OK {def_id} {summary['widgets']} widgets\n")
            return 0

        try:
            result = seeding.install_drafts(root, def_id=def_id)
        except (seeding.SeedError, RepositoryError) as exc:
            self.stderr.write(f"{exc}\n")
            raise SystemExit(1) from exc

        self.stdout.write(
            f"SEEDED {result['def_id']} report={result['report_revision']} "
            f"policy={result['policy_def_id']}@{result['policy_revision']} drafts-only=yes\n"
        )

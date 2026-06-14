# PRIMER — LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Database routing for append-only audit records."""


class AuditRouter:
    """Route audit app models to the separate audit database alias."""

    audit_app_label = "audit"
    audit_db_alias = "audit"

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.audit_app_label:
            return self.audit_db_alias
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.audit_app_label:
            return self.audit_db_alias
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if (
            obj1._meta.app_label == self.audit_app_label
            or obj2._meta.app_label == self.audit_app_label
        ):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == self.audit_app_label:
            return db == self.audit_db_alias
        if db == self.audit_db_alias:
            return False
        return None

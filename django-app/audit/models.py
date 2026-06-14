# PRIMER — LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Models for PHI access audit events."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    """Append-only audit event stored in the separate audit database."""

    class Category(models.TextChoices):
        USER_SELECTED = "UserSelected", "User Selected"
        FILE_UPLOAD = "FileUpload", "File Upload"
        LLM_CALL = "LLMCall", "LLM Call"
        LLM_SUCCESS = "LLMSuccess", "LLM Success"
        LLM_FAILURE = "LLMFailure", "LLM Failure"
        AUDIT_FAILURE = "AuditFailure", "Audit Failure"

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    username = models.CharField(max_length=150, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    category = models.CharField(max_length=32, choices=Category.choices, db_index=True)
    action = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    route = models.CharField(max_length=255, blank=True, default="")
    method = models.CharField(max_length=12, blank=True, default="")
    status_code = models.PositiveIntegerField(null=True, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    task_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    accession_no = models.CharField(max_length=64, blank=True, default="", db_index=True)

    artifact_path = models.CharField(max_length=500, blank=True, default="")
    artifact_sha256 = models.CharField(max_length=64, blank=True, default="")
    artifact_size = models.BigIntegerField(null=True, blank=True)

    event_hash = models.CharField(max_length=64, blank=True, default="")
    previous_hash = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp", "-id"]
        indexes = [
            models.Index(fields=["category", "timestamp"]),
            models.Index(fields=["username", "timestamp"]),
            models.Index(fields=["task_id", "timestamp"]),
            models.Index(fields=["accession_no", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.timestamp.isoformat()} {self.username} {self.category}"

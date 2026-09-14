# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Settings for the throwaway browser dev server (Task 14A layout suite).

Used only via ``DJANGO_SETTINGS_MODULE=report_v2.tests.browser_settings`` when the browser suite
spawns its one-off ``runserver``. It is the production settings minus the deployment hardening knobs
that would fight a loopback dev server, plus the static-files storage backend so ``--insecure`` can
serve the shipped assets. The database locations are supplied by the environment (DATABASE_NAME /
AUDIT_DATABASE_NAME) so this module never hard-codes a path into any real tree.
"""
from __future__ import annotations

import mimetypes as _mimetypes
import os as _os

# Serve ES modules (.mjs) with a JavaScript MIME type so Chromium accepts <script type="module">;
# Python's mimetypes has no default for the .mjs suffix and a wrong type blocks module loading.
_mimetypes.init()
_mimetypes.add_type("text/javascript", "mjs")
_mimetypes.add_type("text/javascript", "js")
_mimetypes.init()

from lunit_audit.settings import *  # noqa: F401,F403

# The production settings never consult an environment variable for the private definition root, so
# a runserver booted from this module would fall back to BASE_DIR/private_data INSIDE the repo and
# write blobs/pointers there. Mirror the harness-provided scratch root here so every durable write
# of the throwaway server lands in its tmp directory instead, and so the suite's on-disk assertions
# (no draft written on an editor GET) observe the very same path.
REPORT_V2_ROOT = _os.environ.get("REPORT_V2_ROOT") or str(
    _os.path.join(_os.environ.get("TMPDIR", "/tmp"), "rv2-browser-definitions"))

# DEBUG=False makes the production settings apply their HTTPS hardening (Secure cookies + SSL
# redirect). The throwaway loopback server is plain http, so those have to be neutralised here or
# the session/CSRF cookies would be dropped by the client and login could never complete.
DEBUG = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

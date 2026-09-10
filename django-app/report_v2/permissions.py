# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Access boundary for the report-v2 catalog and published reports.

The edit rule is the *existing* house admin predicate, copied verbatim from
:func:`upload.views._is_admin` / :func:`viewer.views._is_admin` (which already duplicate it across those
two modules): a user may edit when they are a superuser or a member of the ``admins`` group. Reusing
``user_passes_test`` keeps the decorator behaviour identical to every other privileged view in the project,
and deliberately introduces no new permission model, group or auth scheme.

The view rule is intentionally thin: an authenticated user may view, but only *published* reports. Actual
publication/visibility filtering is owned by the future repository layer (Task 11), not by these
predicates -- ``can_view_published`` only asserts the authentication precondition and
:func:`published_report_only` is a documented convention hook so future views get the login gate by
default. No invented authorization is smuggled in here.
"""

from __future__ import annotations

from typing import Callable

from django.contrib.auth.decorators import login_required, user_passes_test

__all__ = [
    "admin_required",
    "can_edit_catalog",
    "can_view_published",
    "published_report_only",
]


def _is_admin(user) -> bool:
    """Check if user is in the 'admins' group or is a superuser.

    Verbatim copy of the duplicated house predicate in :mod:`upload.views` (lines 33-38) and
    :mod:`viewer.views` (lines 25-28); kept in sync with them on purpose so report-v2 shares the exact same
    edit authority as the rest of the deployment.
    """
    return user.is_superuser or user.groups.filter(name="admins").exists()


# The house decorator convention: build the privileged-view decorator from the predicate exactly as the
# upload/viewer apps do, so ``@admin_required`` behaves identically everywhere.
admin_required = user_passes_test(_is_admin)


def can_edit_catalog(user) -> bool:
    """Whether ``user`` may author/edit catalog and definition content.

    Mirrors the ``admins``-group-or-superuser rule used across the project; there is no separate report-v2
    editor role.
    """
    return bool(_is_admin(user))


def can_view_published(user) -> bool:
    """Whether ``user`` may view the published report surface.

    Any authenticated user qualifies. This only enforces the authentication precondition -- the selection of
    which reports count as "published" is applied by the future repository layer, not here.
    """
    return bool(user.is_authenticated)


def published_report_only(view_func: Callable) -> Callable:
    """Gate a view behind login as the convention for the published-report pages.

    A deliberately thin wrapper over :func:`~django.contrib.auth.decorators.login_required`: it gives future
    report views the authenticated precondition by convention. The published-only visibility check itself is
    layered by the repository when reports are resolved, so this decorator does not invent a second auth
    scheme.
    """
    return login_required(view_func)

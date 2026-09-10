# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Production registry plus the single require-project-context entry point for report-v2 catalogs.

There is exactly one way for runtime code (views, urls, future evaluation tasks) to obtain a project: call
:func:`require_project_context` (or the read helpers on the singleton returned by :func:`production_registry`).
That path can only ever see projects registered through :func:`register_production` -- the production
singleton is bootstrapped with just the PRIME catalog and is *never* consulted by, nor merged with, the
test-only registry. There is deliberately no default project and no cross-project fallback: asking for an
unknown project raises :class:`UnknownProjectError` rather than quietly returning PRIME.

The require guard is also the only component permitted to name a *second* project. When an identifier is
missing from the requested project it checks whether that identifier resolves in exactly one *other*
registered project; if so it raises :class:`CrossProjectReferenceError` naming both projects, otherwise it
re-raises the specific :class:`UnknownError`. This turns a "forgot to switch project" mistake -- reaching
another project's source from a PRIME context -- into a loud failure instead of a silent wrong join.

Test-only registration lives in the same module but on a physically separate, isolated
:class:`ProjectRegistry` instance that production navigation can never reach; the ``*_test_*`` helpers are
documented as such and are never read by :func:`production_registry`.
"""

from __future__ import annotations

import threading
from typing import Callable, Mapping

from .base import (
    CrossProjectReferenceError,
    ProjectCatalogError,
    ProjectDefinition,
    UnknownProjectError,
)
from .prime import PROJECT

__all__ = [
    "ProjectRegistry",
    "production_registry",
    "register_production",
    "require_project_context",
    "register_test_project",
    "test_registry",
    "require_test_project_context",
]

# category -> (project, identifier) -> entry | raises. Each callable delegates to the strict, project-local
# lookup on :class:`ProjectDefinition`, so a miss surfaces the matching typed error from :mod:`.base`.
_PROJECT_LOOKUP: Mapping[str, Callable[[ProjectDefinition, str], object]] = {
    "source": lambda project, identifier: project.source(identifier),
    "outcome": lambda project, identifier: project.outcome(identifier),
    "cohort": lambda project, identifier: project.cohort(identifier),
    "dimension": lambda project, identifier: project.dimension(identifier),
    "measurement": lambda project, identifier: project.measurement(identifier),
    "policy": lambda project, identifier: project.policy(identifier),
}


# ---------------------------------------------------------------------------
# The registry container
# ---------------------------------------------------------------------------
class ProjectRegistry:
    """A mutable name -> :class:`ProjectDefinition` table with strict duplicate handling."""

    def __init__(self) -> None:
        self._definitions: dict[str, ProjectDefinition] = {}

    def register(self, definition: ProjectDefinition, *, allow_overwrite: bool = False) -> None:
        """Add ``definition`` under its ``project_id``.

        Re-registering an existing identifier raises :class:`ProjectCatalogError` unless ``allow_overwrite``
        is set; that flag exists for the test-only helper so repeated test setup is idempotent, never for
        production (which registers each project exactly once at bootstrap).
        """
        project_id = definition.project_id
        if project_id in self._definitions and not allow_overwrite:
            raise ProjectCatalogError(f"project {project_id!r} is already registered")
        self._definitions[project_id] = definition

    def get(self, project_id: str) -> ProjectDefinition | None:
        """Return the definition for ``project_id`` or ``None`` -- never substitutes another project."""
        return self._definitions.get(project_id)

    def ids(self) -> tuple[str, ...]:
        """The registered project identifiers, in insertion order."""
        return tuple(self._definitions)

    def _entries(self):
        """Internal: iterate ``(project_id, definition)`` pairs for the foreign-owner scan."""
        return list(self._definitions.items())


# ---------------------------------------------------------------------------
# Production singleton (lazy, thread-safe, idempotent bootstrap)
# ---------------------------------------------------------------------------
_PRODUCTION_LOCK = threading.Lock()
_PRODUCTION_REGISTRY: ProjectRegistry | None = None


def production_registry() -> ProjectRegistry:
    """Return the process-wide production registry, bootstrapped with exactly the PRIME catalog.

    This is the *only* registry production navigation may read. The singleton is built once under a lock and
    registers the reviewed PRIME definition; it is never merged with, nor populated from, the test registry.
    """
    global _PRODUCTION_REGISTRY
    if _PRODUCTION_REGISTRY is None:
        with _PRODUCTION_LOCK:
            if _PRODUCTION_REGISTRY is None:
                registry = ProjectRegistry()
                registry.register(PROJECT)
                _PRODUCTION_REGISTRY = registry
    return _PRODUCTION_REGISTRY


def register_production(definition: ProjectDefinition) -> None:
    """Register a real project definition into the production singleton.

    Intended for genuine project modules only (the PRIME catalog is already registered at bootstrap); a
    duplicate identifier fails rather than overwriting, so production projects can never be swapped silently.
    """
    production_registry().register(definition)


# ---------------------------------------------------------------------------
# The single require-project-context guard
# ---------------------------------------------------------------------------
def _foreign_owner(
    registry: ProjectRegistry, category: str, identifier: str, *, current_project_id: str
) -> str | None:
    """Return the id of the *one* other registered project that clearly owns ``identifier``, else ``None``.

    A policy reference is matched on its bare ``policy_id`` (the ``@version`` is context-local). If more
    than one other project could own the identifier we treat ownership as ambiguous and report ``None`` so
    the caller raises the plain unknown error rather than a possibly wrong cross-project accusation.
    """
    lookup = _PROJECT_LOOKUP[category]
    probe_id = identifier.partition("@")[0] if category == "policy" else identifier
    owners: list[str] = []
    for project_id, definition in registry._entries():
        if project_id == current_project_id:
            continue
        try:
            lookup(definition, probe_id)
        except ProjectCatalogError:
            continue
        owners.append(project_id)
    if len(owners) == 1:
        return owners[0]
    return None


def require_project_context(
    project_id: str,
    *,
    registry: ProjectRegistry | None = None,
    source_id: str | None = None,
    outcome_id: str | None = None,
    cohort_id: str | None = None,
    dimension_id: str | None = None,
    policy_ref: str | None = None,
    measurement_id: str | None = None,
) -> ProjectDefinition:
    """Resolve ``project_id`` and validate every requested identifier inside *that* project only.

    Fails explicitly -- with no fallback to any other project -- when the project is unknown. For each
    requested identifier it is looked up in the addressed project; a miss is escalated to
    :class:`CrossProjectReferenceError` only when the identifier clearly belongs to exactly one other
    registered project, otherwise the specific :class:`UnknownError` from :mod:`.base` is re-raised. Returns
    the resolved :class:`ProjectDefinition` so callers can keep using it as the validated context.
    """
    resolved_registry = registry if registry is not None else production_registry()
    project = resolved_registry.get(project_id)
    if project is None:
        raise UnknownProjectError(f"unknown project {project_id!r}")

    requested = (
        ("source", source_id),
        ("outcome", outcome_id),
        ("cohort", cohort_id),
        ("dimension", dimension_id),
        ("policy", policy_ref),
        ("measurement", measurement_id),
    )
    lookup_by_category = _PROJECT_LOOKUP
    for category, identifier in requested:
        if identifier is None:
            continue
        try:
            lookup_by_category[category](project, identifier)
        except ProjectCatalogError as exc:
            owner = _foreign_owner(resolved_registry, category, identifier, current_project_id=project_id)
            if owner is not None:
                raise CrossProjectReferenceError(
                    f"{category} {identifier!r} belongs to project {owner!r}, "
                    f"not the requested project {project_id!r}"
                ) from exc
            raise
    return project


# ---------------------------------------------------------------------------
# TEST-ONLY registration surface -- production navigation can NEVER reach these.
#
# ``views``/``urls``/``production_registry()`` read only the production singleton built above. They never
# import, merge, or fall back to ``_TEST_REGISTRY``. Registration here exists purely so the focused catalog
# suite can stand up a second, synthetic project and exercise the cross-project guard without ever being
# able to leak that project into a real request path.
# ---------------------------------------------------------------------------
_TEST_REGISTRY = ProjectRegistry()


def register_test_project(definition: ProjectDefinition) -> None:
    """TEST-ONLY: register a synthetic project into the isolated test registry.

    Must never be called from production code. It populates a registry instance that production navigation
    cannot reach because :func:`production_registry` (and therefore every view/url) reads a different,
    independently bootstrapped singleton. Overwrites are allowed so repeated test set-up stays idempotent.
    """
    _TEST_REGISTRY.register(definition, allow_overwrite=True)


def test_registry() -> ProjectRegistry:
    """TEST-ONLY: return the isolated registry (pre-registered with nothing)."""
    return _TEST_REGISTRY


def require_test_project_context(
    project_id: str,
    *,
    registry: ProjectRegistry | None = None,
    source_id: str | None = None,
    outcome_id: str | None = None,
    cohort_id: str | None = None,
    dimension_id: str | None = None,
    policy_ref: str | None = None,
    measurement_id: str | None = None,
) -> ProjectDefinition:
    """TEST-ONLY: :func:`require_project_context` defaulting to the isolated :func:`test_registry`.

    Identical guard semantics, but resolves against the test registry unless an explicit ``registry`` is
    supplied. Never reachable from production navigation.
    """
    resolved_registry = registry if registry is not None else test_registry()
    return require_project_context(
        project_id,
        registry=resolved_registry,
        source_id=source_id,
        outcome_id=outcome_id,
        cohort_id=cohort_id,
        dimension_id=dimension_id,
        policy_ref=policy_ref,
        measurement_id=measurement_id,
    )

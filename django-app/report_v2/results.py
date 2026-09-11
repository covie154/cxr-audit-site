# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.

"""Frozen, JSON-friendly result envelope for ``report_v2`` measurement widgets.

``results.py`` is the *leaf* module of the report-v2 pipeline.  Every widget
produced by :mod:`report_v2.evaluation` wraps its measurement output in a
:class:`ResultPayload` built from the sections defined here.  The envelope
has two duties:

1. It makes the contract between the evaluator and the widget/UI layer
   explicit and un-bypassable: the four metadata groups -- ``sources``,
   ``versions``, ``dates`` and ``units`` -- must be present and non-empty in
   every published payload, so downstream code can always answer "which
   modules produced this, under which policy/schema version, anchored at
   which date, in which units".
2. It refuses, at construction time rather than at render time, every
   structural mistake that would otherwise leak into a report: aggregate
   widgets carrying raw rows, exclusion partitions that do not reconcile,
   paired widgets whose two sides disagree on the common population, empty
   module lists, non-string unit keys, bools posing as ints, and so on.  All
   such violations surface as :class:`PayloadContractError`.

Because this module is a leaf, it deliberately imports *nothing* from the
project: no Django, no ORM, and not even the sibling ``report_v2`` modules it
describes (``projects`` / ``dates`` / ``measurements`` / ``definitions``) --
those already depend on this envelope via ``evaluation.py`` and importing
them back would create a cycle.  It therefore defines its own tiny local
error base (:class:`ResultsError`) rather than borrowing the evaluator's; the
two bases are intentionally distinct and each only ever describes *its own*
misuse.

Everything the envelope can hold is either a plain JSON scalar, a
:class:`~collections.abc.Mapping`, a :class:`~collections.abc.Sequence`, or a
dedicated dataclass exposing ``as_dict()``.  :func:`json_friendly` is the
recursive normaliser that guarantees a published envelope contains nothing
outside that set: dates become ISO strings, frozensets/sets become sorted
lists, ``Rate``-like measurement results that expose an ``as_dict()`` are
expanded, and unknown scalars pass through untouched rather than raising so
that enum-backed statuses and numpy scalars stay usable by the caller.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

__all__ = [
    "SCHEMA_VERSION",
    "EVALUATOR_NAME",
    "ResultsError",
    "PayloadContractError",
    "SourceMetadata",
    "VersionMetadata",
    "DateMetadata",
    "CountAccounting",
    "CommonPopulation",
    "ResultPayload",
    "json_friendly",
]


# ---------------------------------------------------------------------------
# Typed errors -- local base, deliberately separate from evaluation.py's base
# ---------------------------------------------------------------------------


class ResultsError(Exception):
    """Base for every error raised by the results envelope itself."""


class PayloadContractError(ResultsError):
    """Raised when a payload violates one of its own structural guarantees."""


# ---------------------------------------------------------------------------
# Envelope constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION: int = 1
EVALUATOR_NAME: str = "report_v2.evaluation"


# ---------------------------------------------------------------------------
# Predicate helpers shared by the __post_init__ validators
# ---------------------------------------------------------------------------


def _is_plain_int(value: Any) -> bool:
    """True iff *value* is a real, non-negative ``int`` (bools are refused)."""
    if isinstance(value, bool):
        return False
    return isinstance(value, int) and value >= 0


def _is_non_empty_str(value: Any) -> bool:
    """True iff *value* is a ``str`` carrying at least one non-space char."""
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Recursive JSON normaliser
# ---------------------------------------------------------------------------


def json_friendly(value: Any) -> Any:
    """Return a copy of *value* built only from JSON-safe primitives.

    Mapping             -> dict of normalised values.
    frozenset / set     -> sorted list of normalised elements (stable order).
    Sequence            -> list of normalised elements; ``str`` / ``bytes``
                           short-circuit above and stay scalars.
    date / datetime     -> ISO-formatted string (the envelope never carries
                           date objects so that a payload can be published
                           as-is, without a custom encoder).
    exposes ``as_dict`` -> called recursively (Rate-like measurement results).
    anything else       -> passed through unchanged; we refuse to raise on
                           unknown scalars so enum statuses, numpy scalars and
                           similar remain usable by the caller.
    """
    if isinstance(value, Mapping):
        return {key: json_friendly(item) for key, item in value.items()}
    if isinstance(value, (str, bytes)):
        return value
    if isinstance(value, frozenset):
        return sorted((json_friendly(item) for item in value), key=repr)
    if isinstance(value, Sequence):
        return [json_friendly(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return json_friendly(as_dict())
    return value


# ---------------------------------------------------------------------------
# Envelope sections -- each an independently validatable slice
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SourceMetadata:
    """Provenance block: which ``report_v2`` modules produced this payload.

    ``modules`` lists the dotted module paths -- e.g.
    ``("report_v2.dates", "report_v2.measurements.classification")`` -- that
    actually ran over the data.  It is normalised to a ``tuple`` of non-empty
    ``str`` entries and may not be empty: an anonymous measurement has no
    provenance and is therefore useless for audit, so we reject it at
    construction rather than downstream.
    """

    modules: tuple[str, ...]
    project_id: str

    def __post_init__(self) -> None:
        raw = self.modules
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Iterable):
            raise PayloadContractError(
                "SourceMetadata.modules must be an iterable of non-empty strings"
            )
        normalised: list[str] = []
        for module in raw:
            if not _is_non_empty_str(module):
                raise PayloadContractError(
                    f"SourceMetadata.modules entries must be non-empty strings; "
                    f"got {module!r}"
                )
            normalised.append(module)
        if not normalised:
            raise PayloadContractError(
                "SourceMetadata.modules must not be empty -- a payload always has "
                "to declare which modules produced it"
            )
        if not _is_non_empty_str(self.project_id):
            raise PayloadContractError(
                "SourceMetadata.project_id must be a non-empty string"
            )
        object.__setattr__(self, "modules", tuple(normalised))

    def as_dict(self) -> dict[str, Any]:
        return {"modules": list(self.modules), "project_id": self.project_id}


@dataclass(frozen=True, kw_only=True)
class VersionMetadata:
    """Which policy / schema / evaluator produced the measurement output.

    ``policy_version`` and ``policy_ref`` are ``None`` for widgets that need
    no threshold policy at all (e.g. a plain prevalence count); the schema and
    evaluator versions always default to the constants defined in this module
    so callers never have to remember to bump them.
    """

    policy_version: int | None
    policy_ref: str | None
    schema_version: int = SCHEMA_VERSION
    evaluator_version: str = EVALUATOR_NAME
    measurement_id: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(
            self.schema_version, int
        ):
            raise PayloadContractError(
                f"VersionMetadata.schema_version must be a plain int; "
                f"got {self.schema_version!r}"
            )
        if self.schema_version < 1:
            raise PayloadContractError(
                f"VersionMetadata.schema_version must be >= 1; got "
                f"{self.schema_version}"
            )
        if not _is_non_empty_str(self.measurement_id):
            raise PayloadContractError(
                "VersionMetadata.measurement_id must be a non-empty string"
            )
        if not _is_non_empty_str(self.evaluator_version):
            raise PayloadContractError(
                "VersionMetadata.evaluator_version must be a non-empty string"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_ref": self.policy_ref,
            "schema_version": self.schema_version,
            "evaluator_version": self.evaluator_version,
            "measurement_id": self.measurement_id,
        }


@dataclass(frozen=True, kw_only=True)
class DateMetadata:
    """Date context of a measurement: the anchor ``D`` plus the window it opened.

    Every value is stored as an **ISO string**, never as a
    :class:`datetime.date` -- the envelope must stay JSON-friendly without a
    custom encoder.  A ``None`` anchor simply means there was nothing to
    anchor on (e.g. an empty eligible set); the keys themselves always
    survive :meth:`as_dict` so downstream renderers can rely on their
    presence.
    """

    anchor_date: str | None
    window_start: str | None
    window_end: str | None
    timezone: str
    subgroup_latest_date: str | None = None
    coverage_note: str | None = None

    def __post_init__(self) -> None:
        if not _is_non_empty_str(self.timezone):
            raise PayloadContractError(
                "DateMetadata.timezone must be a non-empty string"
            )

    def as_dict(self) -> dict[str, Any]:
        # Keep ALL six keys even when the values are None: the presence of
        # the key is part of the contract, its value is not.
        return {
            "anchor_date": self.anchor_date,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "timezone": self.timezone,
            "subgroup_latest_date": self.subgroup_latest_date,
            "coverage_note": self.coverage_note,
        }


@dataclass(frozen=True, kw_only=True)
class CountAccounting:
    """Reconciliation ledger from ``incoming`` rows to the ``eligible`` sample.

    The counts form a chain that must close exactly::

        incoming  >=  matching  >=  eligible
        excluded_incomplete == matching - eligible
        sum(excluded_by_reason.values()) == total_dropped == incoming - eligible

    ``excluded_by_reason`` is a **mutually exclusive partition** of every
    dropped row -- a single row is counted under exactly one reason key, so
    the sum of the partition equals the total number of dropped rows.  Any
    drift from that equality means the evaluator either double-counted a row
    or lost one somewhere, so we refuse to build the ledger at all.
    """

    incoming: int
    matching: int
    eligible: int
    excluded_incomplete: int
    excluded_by_reason: Mapping[str, int]

    def __post_init__(self) -> None:
        for label in ("incoming", "matching", "eligible", "excluded_incomplete"):
            value = getattr(self, label)
            if not _is_plain_int(value):
                raise PayloadContractError(
                    f"CountAccounting.{label} must be a non-negative int "
                    f"(bools refused); got {value!r}"
                )
        if not (self.eligible <= self.matching <= self.incoming):
            raise PayloadContractError(
                "CountAccounting must satisfy eligible <= matching <= incoming; "
                f"got eligible={self.eligible}, matching={self.matching}, "
                f"incoming={self.incoming}"
            )
        expected_incomplete = self.matching - self.eligible
        if self.excluded_incomplete != expected_incomplete:
            raise PayloadContractError(
                "CountAccounting.excluded_incomplete must equal matching - "
                f"eligible; got {self.excluded_incomplete} "
                f"expected {expected_incomplete}"
            )
        if not isinstance(self.excluded_by_reason, Mapping):
            raise PayloadContractError(
                "CountAccounting.excluded_by_reason must be a Mapping[str, int]"
            )
        for reason, count in self.excluded_by_reason.items():
            if not _is_non_empty_str(reason):
                raise PayloadContractError(
                    f"CountAccounting.excluded_by_reason keys must be non-empty "
                    f"strings; got {reason!r}"
                )
            if not _is_plain_int(count):
                raise PayloadContractError(
                    f"CountAccounting.excluded_by_reason[{reason!r}] must be a "
                    f"non-negative int (bools refused); got {count!r}"
                )
        partition_sum = sum(self.excluded_by_reason.values())
        if partition_sum != self.total_dropped:
            raise PayloadContractError(
                "CountAccounting.excluded_by_reason must be a mutually exclusive "
                f"partition summing to total_dropped; got sum={partition_sum} "
                f"vs total_dropped={self.total_dropped}"
            )

    @property
    def total_dropped(self) -> int:
        return self.incoming - self.eligible

    def as_dict(self) -> dict[str, Any]:
        return {
            "incoming": self.incoming,
            "matching": self.matching,
            "eligible": self.eligible,
            "excluded_incomplete": self.excluded_incomplete,
            "excluded_by_reason": {
                reason: count
                for reason, count in self.excluded_by_reason.items()
                if count > 0
            },
            "total_dropped": self.total_dropped,
        }


@dataclass(frozen=True, kw_only=True)
class CommonPopulation:
    """Proof that a paired widget measured both sides on the *same* rows.

    McNemar's test and Cohen's kappa are only valid when the reference side
    and the prediction side were computed on the identical set of complete
    rows.  This class captures that equality structurally: every side in
    ``sides`` must have a count exactly equal to ``n_complete``.  If a
    future regression causes one side to silently drop an extra row, the
    construction fails here rather than corrupting the statistic.
    """

    filter_identity: str
    n_complete: int
    sides: Mapping[str, int]

    def __post_init__(self) -> None:
        if not _is_non_empty_str(self.filter_identity):
            raise PayloadContractError(
                "CommonPopulation.filter_identity must be a non-empty string"
            )
        if not _is_plain_int(self.n_complete):
            raise PayloadContractError(
                f"CommonPopulation.n_complete must be a non-negative int "
                f"(bools refused); got {self.n_complete!r}"
            )
        if not isinstance(self.sides, Mapping) or not self.sides:
            raise PayloadContractError(
                "CommonPopulation.sides must be a non-empty Mapping[str, int]"
            )
        for side, count in self.sides.items():
            if not _is_non_empty_str(side):
                raise PayloadContractError(
                    f"CommonPopulation.sides keys must be non-empty strings; "
                    f"got {side!r}"
                )
            if not _is_plain_int(count):
                raise PayloadContractError(
                    f"CommonPopulation.sides[{side!r}] must be a non-negative "
                    f"int (bools refused); got {count!r}"
                )
            if count != self.n_complete:
                raise PayloadContractError(
                    "CommonPopulation is only valid for PAIRED widgets whose "
                    f"sides agree exactly: side {side!r}={count} disagrees with "
                    f"n_complete={self.n_complete}"
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "filter_identity": self.filter_identity,
            "n_complete": self.n_complete,
            "sides": {side: count for side, count in self.sides.items()},
        }


# ---------------------------------------------------------------------------
# Top-level envelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ResultPayload:
    """The single envelope every report-v2 widget publishes.

    A payload is composed of three slices:

    * **measurement output** -- ``aggregates`` plus optional ``rows``,
      ``buckets``, ``groups``, ``pagination`` and ``ci``.  Raw ``rows`` are
      allowed only for non-aggregate (case-level) widgets and are rejected
      up-front otherwise, so an aggregate widget can never leak row-level
      data into a report.
    * **accounting** -- ``counts`` (:class:`CountAccounting`), plus the
      optional :class:`CommonPopulation` for paired widgets.
    * **the four required metadata groups** -- ``sources``, ``versions``,
      ``dates`` and ``units``.  :meth:`to_dict` refuses to publish a payload
      whose groups are not all populated.
    """

    widget_id: str
    display: str
    aggregate: bool
    aggregates: Mapping[str, Any]
    rows: tuple[Mapping[str, Any], ...] = ()
    counts: CountAccounting | None = None
    sources: SourceMetadata | None = None
    versions: VersionMetadata | None = None
    dates: DateMetadata | None = None
    units: Mapping[str, str] | None = None
    ci: Mapping[str, Any] = field(default_factory=dict)
    common_population: CommonPopulation | None = None
    pagination: Mapping[str, Any] | None = None
    buckets: tuple[Mapping[str, Any], ...] = ()
    groups: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _is_non_empty_str(self.widget_id):
            raise PayloadContractError(
                f"ResultPayload.widget_id must be a non-empty string; "
                f"got {self.widget_id!r}"
            )
        if not _is_non_empty_str(self.display):
            raise PayloadContractError(
                f"ResultPayload.display must be a non-empty string; "
                f"got {self.display!r}"
            )
        if not isinstance(self.aggregate, bool):
            raise PayloadContractError(
                f"ResultPayload.aggregate must be a bool; got {self.aggregate!r}"
            )
        if not isinstance(self.aggregates, Mapping):
            raise PayloadContractError(
                "ResultPayload.aggregates must be a Mapping[str, Any]"
            )
        if not isinstance(self.rows, tuple) or any(
            not isinstance(row, Mapping) for row in self.rows
        ):
            raise PayloadContractError(
                "ResultPayload.rows must be a tuple of Mappings[str, Any]"
            )
        if not isinstance(self.counts, CountAccounting):
            raise PayloadContractError(
                "ResultPayload.counts must be a CountAccounting instance"
            )
        if not isinstance(self.sources, SourceMetadata):
            raise PayloadContractError(
                "ResultPayload.sources must be a SourceMetadata instance"
            )
        if not isinstance(self.versions, VersionMetadata):
            raise PayloadContractError(
                "ResultPayload.versions must be a VersionMetadata instance"
            )
        if not isinstance(self.dates, DateMetadata):
            raise PayloadContractError(
                "ResultPayload.dates must be a DateMetadata instance"
            )
        if not isinstance(self.units, Mapping) or not self.units:
            raise PayloadContractError(
                "ResultPayload.units must be a non-empty Mapping[str, str]"
            )
        for key, value in self.units.items():
            if not _is_non_empty_str(key) or not isinstance(value, str):
                raise PayloadContractError(
                    "ResultPayload.units must map non-empty str -> str; got "
                    f"{key!r} -> {value!r}"
                )
        if self.aggregate and self.rows:
            raise PayloadContractError(
                "aggregate widget payloads must not carry raw rows"
            )

    # -- snapshots ---------------------------------------------------------

    def _build_envelope(self) -> dict[str, Any]:
        """Return the fully normalised envelope dict (no publish-time checks)."""
        return {
            "widget_id": self.widget_id,
            "display": self.display,
            "aggregate": self.aggregate,
            "aggregates": json_friendly(self.aggregates),
            "rows": (
                [] if self.aggregate
                else [json_friendly(row) for row in self.rows]
            ),
            "counts": self.counts.as_dict(),
            "sources": self.sources.as_dict(),
            "versions": self.versions.as_dict(),
            "dates": self.dates.as_dict(),
            "units": {key: value for key, value in self.units.items()},
            "ci": json_friendly(self.ci),
            "common_population": (
                None if self.common_population is None
                else self.common_population.as_dict()
            ),
            "pagination": json_friendly(self.pagination),
            "buckets": [json_friendly(bucket) for bucket in self.buckets],
            "groups": list(self.groups),
        }

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-friendly snapshot without the publish-time checks."""
        return self._build_envelope()

    def to_dict(self) -> dict[str, Any]:
        """The published envelope. ALWAYS carries the four metadata groups.

        The four required groups -- ``sources`` / ``versions`` / ``dates`` /
        ``units`` -- are checked after the snapshot is built.  ``sources`` is
        gated via its ``modules`` list, ``versions`` and ``dates`` via their
        dict-truthiness (``dates`` is always truthy as a *mapping* because it
        always carries its keys -- the effective gate there is that the section
        object was constructable at all), and ``units`` via dict-truthiness
        again.  A missing/empty group is a publish-time contract violation and
        raises :class:`PayloadContractError`.
        """
        out = self._build_envelope()
        for label, gate in (
            ("sources", out["sources"]["modules"]),
            ("versions", out["versions"]),
            ("dates", out["dates"]),
            ("units", out["units"]),
        ):
            if not gate:
                raise PayloadContractError(
                    f"ResultPayload.to_dict: required metadata group "
                    f"{label!r} must be non-empty"
                )
        return out


# ---------------------------------------------------------------------------
# Self-checks -- run with ``python report_v2/results.py`` (plain python).
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    # Minimal, internally consistent accounting ledger:
    #   incoming=5, matching=3, eligible=2 -> total_dropped=3
    #   excluded_incomplete=1 == matching - eligible = 1
    #   per-reason partition {missing_required:2, out_of_window:1} sums to 3
    def _counts(**overrides: Any) -> CountAccounting:
        defaults: dict[str, Any] = {
            "incoming": 5,
            "matching": 3,
            "eligible": 2,
            "excluded_incomplete": 1,
            "excluded_by_reason": {"missing_required": 2, "out_of_window": 1},
        }
        defaults.update(overrides)
        return CountAccounting(**defaults)

    def _payload(**overrides: Any) -> ResultPayload:
        defaults: dict[str, Any] = {
            "widget_id": "widget.prevalence",
            "display": "value",
            "aggregate": True,
            "aggregates": {"value": 0.5, "ci_low": 0.2, "ci_high": 0.8},
            "rows": (),
            "counts": _counts(),
            "sources": SourceMetadata(
                modules=(
                    "report_v2.dates",
                    "report_v2.measurements.classification",
                ),
                project_id="project.demo",
            ),
            "versions": VersionMetadata(
                policy_version=3,
                policy_ref="policy:v3",
                measurement_id="measurement.prevalence",
            ),
            "dates": DateMetadata(
                anchor_date="2026-09-10",
                window_start="2026-08-11",
                window_end="2026-09-10",
                timezone="UTC",
            ),
            "units": {"value": "ratio", "ci_low": "ratio", "ci_high": "ratio"},
        }
        defaults.update(overrides)
        return ResultPayload(**defaults)

    def _expect_contract_error(builder: Any, label: str) -> PayloadContractError:
        try:
            builder()
        except PayloadContractError as exc:
            return exc
        raise AssertionError(f"{label}: expected PayloadContractError to be raised")

    # -- 1. minimal valid aggregate payload publishes all four metadata groups
    published = _payload().to_dict()
    assert published["widget_id"] == "widget.prevalence"
    assert published["aggregate"] is True
    assert published["sources"]["modules"] == [
        "report_v2.dates",
        "report_v2.measurements.classification",
    ], published["sources"]
    assert published["versions"]["measurement_id"] == "measurement.prevalence"
    assert set(published["dates"]) == {
        "anchor_date",
        "window_start",
        "window_end",
        "timezone",
        "subgroup_latest_date",
        "coverage_note",
    }, published["dates"]
    assert published["dates"]["subgroup_latest_date"] is None  # all six keys kept
    assert published["units"] == {
        "value": "ratio",
        "ci_low": "ratio",
        "ci_high": "ratio",
    }
    assert published["counts"]["total_dropped"] == 3
    assert published["common_population"] is None
    # Aggregate widgets publish [] for rows -- never the raw tuple, even if one
    # were smuggled in via a subclass that bypasses __post_init__.
    assert published["rows"] == []
    # as_dict and to_dict agree on the shape.
    assert ResultPayload(**_payload().__dict__).as_dict().keys() == published.keys()

    # -- 2. non-aggregate payloads round-trip their case-level rows ----------
    case_rows = ({"accession_no": 1}, {"accession_no": 2})
    case_out = _payload(
        aggregate=False, display="table", rows=case_rows
    ).to_dict()
    assert case_out["aggregate"] is False
    assert [row["accession_no"] for row in case_out["rows"]] == [1, 2]

    # -- 3. aggregate payload that carries raw rows is refused ---------------
    _expect_contract_error(
        lambda: _payload(rows=({"accession_no": 1},)),
        "aggregate payload with raw rows",
    )

    # -- 4. the count-reconciliation gate rejects a broken partition ---------
    _expect_contract_error(
        lambda: _counts(excluded_by_reason={"missing_required": 99}),
        "per-reason partition not summing to total_dropped",
    )
    _expect_contract_error(
        lambda: _counts(excluded_incomplete=0),
        "excluded_incomplete != matching - eligible",
    )
    _expect_contract_error(
        lambda: _counts(eligible=4),  # eligible > matching is impossible
        "eligible greater than matching",
    )
    _expect_contract_error(
        lambda: _counts(incoming=True),  # bool masquerading as an int
        "bool in a counting field",
    )
    _expect_contract_error(
        lambda: _counts(excluded_by_reason={"": 3}),  # empty reason key
        "empty exclusion reason key",
    )

    # -- 5. CommonPopulation rejects paired sides that disagree ---------------
    _expect_contract_error(
        lambda: CommonPopulation(
            filter_identity="shared-filter",
            n_complete=42,
            sides={"reference": 42, "prediction": 41},
        ),
        "paired sides disagree on n_complete",
    )
    paired = CommonPopulation(
        filter_identity="shared-filter",
        n_complete=42,
        sides={"reference": 42, "prediction": 42},
    )
    assert paired.as_dict()["sides"] == {"reference": 42, "prediction": 42}
    paired_payload = _payload(
        widget_id="widget.agreement",
        display="table",
        common_population=paired,
    ).to_dict()
    assert paired_payload["common_population"]["filter_identity"] == "shared-filter"

    # -- 6. SourceMetadata refuses an empty / malformed module list ----------
    _expect_contract_error(
        lambda: SourceMetadata(modules=(), project_id="project.demo"),
        "SourceMetadata with empty modules",
    )
    _expect_contract_error(
        lambda: SourceMetadata(modules=("  ",), project_id="project.demo"),
        "SourceMetadata with whitespace-only module name",
    )
    normalised = SourceMetadata(
        modules=["report_v2.dates", "report_v2.measurements.classification"],
        project_id="project.demo",
    )
    assert isinstance(normalised.modules, tuple)  # list normalised to tuple

    # -- 7. ResultPayload structural guards ----------------------------------
    _expect_contract_error(
        lambda: _payload(units={}),
        "ResultPayload with empty units",
    )
    _expect_contract_error(
        lambda: _payload(units={"value": 1.0}),  # unit values must be str
        "ResultPayload with non-str unit value",
    )
    _expect_contract_error(
        lambda: _payload(rows=({"accession_no": 1},)),  # not a tuple of Mappings
        "aggregate payload with raw rows (again)",
    )
    _expect_contract_error(
        lambda: _payload(rows=[{"accession_no": 1}]),  # list, not tuple
        "rows supplied as list rather than tuple",
    )

    # -- 8. json_friendly covers the documented coercions ---------------------
    class _Rate:  # stand-in for a Rate-like measurement result
        def as_dict(self) -> dict[str, Any]:
            return {"numerator": 3, "denominator": 5, "value": 0.6}

    normalised = json_friendly(
        {
            "when": datetime(2026, 9, 10, 12, 30, 0),
            "day": date(2026, 9, 10),
            "tags": frozenset({"b", "a", "c"}),
            "nested": [{"k": frozenset({2, 1})}],
            "rate": _Rate(),
            "text": "raw",
            "unknown": 3.14,
        }
    )
    assert normalised["when"] == "2026-09-10T12:30:00"
    assert normalised["day"] == "2026-09-10"
    assert normalised["tags"] == ["a", "b", "c"]
    assert normalised["nested"] == [{"k": [1, 2]}]
    assert normalised["rate"] == {"numerator": 3, "denominator": 5, "value": 0.6}
    assert normalised["text"] == "raw"
    assert normalised["unknown"] == 3.14  # unknown scalars pass through

    print("report_v2.results: all self-checks passed")

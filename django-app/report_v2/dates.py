# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Pure, side-effect-free calendar window, query-boundary and bucketing resolution for the report-v2 layer.

This module turns an *already captured* anchor date ``D`` (plus the project's IANA timezone name) into an
immutable :class:`ResolvedWindow`, timezone-aware :class:`QueryBoundaries` for a later ORM range query, and a
:class:`Bucket` sequence over an arbitrary span -- all with **no** ORM, no persisted object and no database
access. Windows are computed from the calendar alone: relative tokens (``D`` / ``W`` / ``M`` / ``Y`` with
optional ``-n`` offsets) resolve *against the anchor*, never against the wall clock, so a widget's published
range can never drift between two renderings of the same snapshot.

Design rules relied upon by the rest of the layer:

* **Nothing here may compute "today" at call time.** The anchor is captured exactly once, server-side, as the
  latest *complete, eligible* event date for a widget; wall-clock drift must never move a published window.
  Every public entry point therefore takes ``D`` explicitly as a ``datetime.date``; a missing/``None`` anchor
  is a hard :class:`MissingAnchorError`, never a silently filled-in wall-clock reading taken at call time. The
  module imports only the standard library (``datetime`` / ``zoneinfo`` / ``dataclasses`` / ``typing``) and is
  ORM-free by construction -- it never touches the ORM, a persisted object, a database handle or the environment.
* Calendar periods are anchored on fixed boundaries: ``W`` is the Monday of the anchor week, ``M`` the first
  day of the anchor month, ``Y`` the first of January of the anchor year; the ``-n`` forms simply extend those
  rules back by ``n`` non-negative units. An offset that is negative or not an integer is a typed
  :class:`InvalidOffsetError`; an unparseable token is a typed :class:`InvalidWindowError`.
* **Explicit dates stay explicit.** An ISO start/end override is returned verbatim -- it is never shifted,
  clamped or truncated toward the anchor, even when it names a future date. A caller reads such a range as
  empty / coverage-limited (see :attr:`ResolvedWindow.ends_after_anchor`) rather than the range being rewritten.
  A reversed range, a mixed relative start that does not end at the anchor, and an impossible calendar literal
  (``2026-02-30`` -- rejected by constructing a real :class:`datetime.date`, not by a regex) all fail loudly.
* The anchor cannot be moved by a reader. :func:`capture_anchor` derives ``D`` from the latest complete,
  eligible candidate supplied by the caller (returning ``None`` -- not a fabricated date, not "now" -- when
  nothing qualifies), and :func:`resolve_request` resolves a reader request against an *already captured*
  anchor while *ignoring* any reader-submitted ``anchor`` / ``D`` / ``as_of`` field. A subgroup narrowing is
  reported as an informational coverage value and never relocates the window.
* Every returned structure is an immutable, frozen :mod:`dataclasses` value object exposing ``as_dict()``,
  mirroring :mod:`report_v2.measurements.predictions`; nothing returned can be mutated by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone as _dt_timezone
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

__all__ = [
    "BUCKET_SIZES",
    "WEEK_START_WEEKDAY",
    "DateRangeError",
    "MissingAnchorError",
    "InvalidAnchorError",
    "InvalidWindowError",
    "InvalidOffsetError",
    "UnknownBucketError",
    "InvalidDateLiteralError",
    "InvalidTimezoneError",
    "Anchor",
    "ResolvedWindow",
    "QueryBoundaries",
    "Bucket",
    "capture_anchor",
    "resolve_relative_window",
    "resolve_window",
    "resolve_request",
    "resolve_query_boundaries",
    "localise_day_start",
    "localise_day_end",
    "bucket_range",
]

#: The closed bucket vocabulary a time-series line chart may select (admin-controlled, fixed sizes).
BUCKET_SIZES = frozenset({"day", "week", "month", "year"})
#: ``date.weekday()`` index of Monday -- every ``W`` bucket and ``W`` window starts here.
WEEK_START_WEEKDAY = 0
#: Relative-window base forms and the calendar rule each one names.
_RELATIVE_BASES = ("D", "W", "M", "Y")
#: Reader-supplied keys that attempt to submit / move the anchor; they are always ignored.
_FORBIDDEN_REQUEST_KEYS = frozenset({"anchor", "captured_anchor", "capturedanchor", "d", "as_of", "asof", "asofdate"})


# ---------------------------------------------------------------------------
# Error model (mirrors the predictions.PolicyEvaluationError / base.ProjectCatalogError shape).
# ---------------------------------------------------------------------------
class DateRangeError(Exception):
    """Common base for every date-window resolution rejection.

    Carries a single human ``message`` plus a stable machine-readable ``kind`` discriminator that subclasses
    override. The string form prefixes the message with the ``kind`` so logs and editors can triage without
    parsing. The constructor is ``Exception.__init__(message)``-compatible so a subclass is built with a single
    positional message (``InvalidWindowError("...")``).
    """

    kind = "date-range"

    def __init__(self, message: str) -> None:
        self.message = str(message)
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.kind}] {self.message}"


class MissingAnchorError(DateRangeError):
    """A required captured anchor was ``None`` -- there is no eligible data to anchor on.

    This is the deliberate "no today / no now fallback" gate: a caller that has nothing complete and eligible
    must show no eligible data, it must never resolve a window against the wall clock.
    """

    kind = "missing-anchor"


class InvalidAnchorError(DateRangeError):
    """A supplied anchor is present but is not a coherent calendar date."""

    kind = "invalid-anchor"


class InvalidWindowError(DateRangeError):
    """A resolved / explicit window is reversed, mixes a relative start with a non-anchor end, or the token is not parseable."""

    kind = "invalid-window"


class InvalidOffsetError(DateRangeError):
    """A ``-n`` relative offset was negative or not an integer."""

    kind = "invalid-offset"


class UnknownBucketError(DateRangeError):
    """A requested bucket size is outside the fixed ``day`` / ``week`` / ``month`` / ``year`` vocabulary."""

    kind = "unknown-bucket"


class InvalidDateLiteralError(DateRangeError):
    """An explicit date override is malformed or names an impossible calendar day (rejected by the date constructor)."""

    kind = "invalid-date-literal"


class InvalidTimezoneError(DateRangeError):
    """A project timezone name could not be resolved to an IANA zone through :class:`zoneinfo.ZoneInfo`."""

    kind = "invalid-timezone"


# ---------------------------------------------------------------------------
# Internal coercion / parsing helpers (no wall-clock reads anywhere).
# ---------------------------------------------------------------------------
def _is_pure_date(value: object) -> bool:
    """True only for a genuine calendar ``date`` (a ``datetime`` is accepted but normalised by callers)."""
    return isinstance(value, date)  # ``datetime`` is a ``date`` subclass -- acceptable, normalised downstream.


def _coerce_date(value: object, *, error: type[DateRangeError], what: str) -> date:
    """Return ``value`` as a plain :class:`datetime.date`, raising ``error`` on anything else.

    A ``datetime`` is accepted (it is a ``date`` subclass) and reduced to its date part so downstream calendar
    arithmetic and comparisons always operate on pure dates.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise error(f"{what} must be a datetime.date, got {type(value).__name__}")


def _coerce_anchor(anchor: object) -> date:
    """Coerce an anchor argument to a plain date, mapping ``None`` to :class:`MissingAnchorError`.

    ``None`` is *not* filled in with "now" -- it means there was no eligible event date and the caller must
    show no data. A non-date value is an :class:`InvalidAnchorError`. An :class:`Anchor` value object is
    transparently unwrapped to its captured date.
    """
    if anchor is None:
        raise MissingAnchorError("no anchor was captured; a window cannot be resolved against the wall clock")
    if isinstance(anchor, Anchor):
        return anchor.date
    return _coerce_date(anchor, error=InvalidAnchorError, what="anchor")


def parse_date_literal(value: object, *, what: str = "date literal") -> date:
    """Parse an explicit ISO override into a real :class:`datetime.date`, rejecting impossible days.

    ``value`` may already be a ``date``/``datetime`` (returned normalised) or an ``YYYY-MM-DD`` string. An
    impossible calendar day such as ``"2026-02-30"`` is rejected **semantically** by constructing a genuine
    :class:`datetime.date` (the ``ValueError`` the constructor raises is caught and re-raised as the typed
    :class:`InvalidDateLiteralError`) -- there is no regex that "looks like" a date and is trusted.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return date.fromisoformat(text)
        except (ValueError, TypeError) as exc:
            raise InvalidDateLiteralError(f"{what} {value!r} is not a valid ISO calendar date: {exc}") from None
    raise InvalidDateLiteralError(f"{what} must be a datetime.date or an ISO date string, got {type(value).__name__}")


def _tzinfo(timezone: object) -> ZoneInfo:
    """Resolve an IANA timezone *name* through :class:`zoneinfo.ZoneInfo` (stdlib, framework-free).

    Only a string name is accepted so the caller is explicit about the project zone; a non-string or an
    unresolvable name is an :class:`InvalidTimezoneError`.
    """
    if not isinstance(timezone, str) or not timezone.strip():
        raise InvalidTimezoneError(f"timezone must be a non-empty IANA name string, got {timezone!r}")
    try:
        return ZoneInfo(timezone.strip())
    except (ValueError, OSError, Exception) as exc:  # ZoneInfoNotFoundError derives from ValueError / KeyError.
        raise InvalidTimezoneError(f"unknown IANA timezone {timezone!r}: {exc}") from None


def _week_start(d: date) -> date:
    """Monday of the Monday-start calendar week containing ``d``."""
    return d - timedelta(days=d.weekday())


def _week_end(d: date) -> date:
    """Sunday (inclusive) of the Monday-start calendar week containing ``d``."""
    return _week_start(d) + timedelta(days=6)


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _month_end(d: date) -> date:
    first = _month_start(d)
    year, month = (first.year + 1, 1) if first.month == 12 else (first.year, first.month + 1)
    return date(year, month, 1) - timedelta(days=1)


def _shift_months(first_of_month: date, months: int) -> date:
    """First day of the month ``months`` months before ``first_of_month`` (``months`` >= 0)."""
    total = first_of_month.year * 12 + (first_of_month.month - 1) - months
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


def _year_start(d: date) -> date:
    return date(d.year, 1, 1)


def _year_end(d: date) -> date:
    return date(d.year, 12, 31)


def _normalise_token(token: object) -> tuple[str, int]:
    """Split a relative token into ``(base, offset)`` with ``base`` in ``_RELATIVE_BASES`` and ``offset`` >= 0.

    ``"D"`` -> ``("D", 0)``; ``"W-1"`` -> ``("W", 1)``. A base outside the vocabulary is an
    :class:`InvalidWindowError` (an unparseable token); a malformed, non-integer or negative ``-n`` offset is an
    :class:`InvalidOffsetError`.
    """
    if not isinstance(token, str):
        raise InvalidWindowError(f"relative window token must be a string, got {type(token).__name__}")
    text = token.strip().upper()
    if not text:
        raise InvalidWindowError("relative window token is empty")
    base, sep, rest = text.partition("-")
    if base not in _RELATIVE_BASES:
        raise InvalidWindowError(f"unknown relative window token {token!r}; expected one of {list(_RELATIVE_BASES)}")
    if not sep:
        return base, 0
    try:
        offset = int(rest)
    except (ValueError, TypeError):
        raise InvalidOffsetError(f"relative token {token!r} has a non-integer offset {rest!r}") from None
    if offset < 0:
        raise InvalidOffsetError(f"relative token {token!r} has a negative offset {offset!r}; offsets are non-negative")
    return base, offset


def _relative_start_date(token: object, anchor: date) -> date:
    """Resolve a relative token to its inclusive *start* date against ``anchor`` (the end is always the anchor).

    ``D``/``D-n`` -> anchor minus ``n`` days (``D-7`` is eight inclusive dates through the anchor).
    ``W``/``W-n`` -> Monday of the anchor week, ``n`` weeks earlier.
    ``M``/``M-n`` -> first of the anchor month, ``n`` months earlier.
    ``Y``/``Y-n`` -> first of January of the anchor year, ``n`` years earlier.
    """
    base, offset = _normalise_token(token)
    if base == "D":
        return anchor - timedelta(days=offset)
    if base == "W":
        return _week_start(anchor) - timedelta(days=7 * offset)
    if base == "M":
        return _shift_months(_month_start(anchor), offset)
    # base == "Y"
    return date(anchor.year - offset, 1, 1)


def _is_anchor_token(value: object) -> bool:
    """True when ``value`` names the anchor explicitly as the ``"D"`` end token."""
    return isinstance(value, str) and value.strip().upper() == "D"


def _coverage_note(start_date: date, end_date: date, subgroup_latest: date | None) -> str:
    """Render the human coverage string, appending a subgroup-limits clause only when the subgroup is older."""
    base = f"coverage {start_date.isoformat()}..{end_date.isoformat()}"
    if subgroup_latest is not None and subgroup_latest < end_date:
        return f"{base}; selected subgroup available through {subgroup_latest.isoformat()}"
    return base


# ---------------------------------------------------------------------------
# Value objects (frozen, JSON-friendly -- mirror the predictions result objects).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Anchor:
    """The immutable, server-captured anchor: a single calendar date plus the project zone it belongs to.

    The anchor is captured once from the latest complete, eligible event date. It carries no notion of the
    wall clock; a reader can never move it because resolution always consumes an *already built* ``Anchor`` (or
    its date), never a reader field.
    """

    date: date
    timezone: str = "Asia/Singapore"
    provenance: str | None = None

    def __post_init__(self) -> None:
        normalised = _coerce_date(self.date, error=InvalidAnchorError, what="anchor date")
        object.__setattr__(self, "date", normalised)
        if not isinstance(self.timezone, str) or not self.timezone.strip():
            raise InvalidAnchorError(f"anchor timezone must be a non-empty IANA name, got {self.timezone!r}")
        # Fail fast at capture time: an unresolvable zone is rejected here rather than at render time.
        _tzinfo(self.timezone)

    def as_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "timezone": self.timezone,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class ResolvedWindow:
    """The immutable inclusive ``[start_date, end_date]`` window resolved against the captured anchor.

    ``start_date``/``end_date`` are inclusive calendar dates. ``anchor`` is retained so coverage relative to the
    captured date can be reported without a second lookup, and ``ends_after_anchor`` / ``starts_after_anchor``
    are the coverage flags a caller reads to decide whether a (possibly explicit, possibly future) range should
    render as data or as an empty / coverage-limited result -- the range itself is *never* rewritten.
    """

    start_date: date
    end_date: date
    anchor: date
    timezone: str
    #: The relative token when this window came from a relative expression; ``None`` for an explicit window.
    token: str | None = None
    #: ``True`` when the range was an explicit ISO override (returned verbatim, never clamped to the anchor).
    explicit: bool = False
    #: Informational only: the selected subgroup's latest eligible date (does not move the window).
    subgroup_latest_eligible_date: date | None = None

    def __post_init__(self) -> None:
        start = _coerce_date(self.start_date, error=InvalidWindowError, what="window start")
        end = _coerce_date(self.end_date, error=InvalidWindowError, what="window end")
        anchor = _coerce_date(self.anchor, error=InvalidAnchorError, what="anchor")
        if end < start:
            raise InvalidWindowError(
                f"reversed window: start {start.isoformat()} is after end {end.isoformat()}"
            )
        subgroup = self.subgroup_latest_eligible_date
        if subgroup is not None:
            subgroup = _coerce_date(
                subgroup, error=InvalidWindowError, what="subgroup latest eligible date"
            )
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)
        object.__setattr__(self, "anchor", anchor)
        object.__setattr__(self, "subgroup_latest_eligible_date", subgroup)

    @property
    def day_count(self) -> int:
        """Number of inclusive calendar dates covered by the window."""
        return (self.end_date - self.start_date).days + 1

    @property
    def starts_after_anchor(self) -> bool:
        """Coverage flag: the window begins after the captured anchor (a future / empty-start range)."""
        return self.start_date > self.anchor

    @property
    def ends_after_anchor(self) -> bool:
        """Coverage flag: the window ends after the captured anchor (a future, coverage-limited range)."""
        return self.end_date > self.anchor

    @property
    def coverage_note(self) -> str:
        return _coverage_note(self.start_date, self.end_date, self.subgroup_latest_eligible_date)

    def as_dict(self) -> dict:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "anchor": self.anchor.isoformat(),
            "timezone": self.timezone,
            "token": self.token,
            "explicit": self.explicit,
            "day_count": self.day_count,
            "starts_after_anchor": self.starts_after_anchor,
            "ends_after_anchor": self.ends_after_anchor,
            "subgroup_latest_eligible_date": (
                self.subgroup_latest_eligible_date.isoformat()
                if self.subgroup_latest_eligible_date is not None
                else None
            ),
            "coverage_note": self.coverage_note,
        }


@dataclass(frozen=True)
class QueryBoundaries:
    """Timezone-aware, inclusive ``[query_start, query_end]`` instants ready for an ORM ``between`` range query.

    ``query_start`` is local ``00:00:00`` on ``start_date`` and ``query_end`` is local ``23:59:59.999999`` on
    ``end_date``, both localised in the project zone through ``zoneinfo``. This structure is *produced* without
    importing any ORM -- a later adapter may build the actual range predicate from these two aware datetimes.
    """

    start_date: date
    end_date: date
    timezone: str
    query_start: datetime
    query_end: datetime

    def __post_init__(self) -> None:
        if self.query_start.tzinfo is None or self.query_end.tzinfo is None:
            raise InvalidTimezoneError("query boundaries must be timezone-aware (tzinfo is not None)")
        if self.query_end < self.query_start:
            raise InvalidWindowError("query_end precedes query_start")

    @property
    def instant_span(self) -> timedelta:
        return self.query_end - self.query_start

    @property
    def query_start_iso(self) -> str:
        return self.query_start.isoformat()

    @property
    def query_end_iso(self) -> str:
        return self.query_end.isoformat()

    def as_dict(self) -> dict:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "timezone": self.timezone,
            "query_start": self.query_start.isoformat(),
            "query_end": self.query_end.isoformat(),
            "query_start_utc": self.query_start.astimezone(_dt_timezone.utc).isoformat().replace("+00:00", "Z"),
            "query_end_utc": self.query_end.astimezone(_dt_timezone.utc).isoformat().replace("+00:00", "Z"),
        }


@dataclass(frozen=True)
class Bucket:
    """One calendar bucket over an arbitrary span, labelled and flagged ``partial`` when its natural period is clipped.

    ``period_start`` / ``period_end`` are the *natural* calendar boundaries (Monday..Sunday, first-of-month..
    end-of-month, Jan-1..Dec-31) and the inclusive ``start_date`` / ``end_date`` are the intersection of that
    period with the requested span. ``partial`` is ``True`` exactly when the natural period extends beyond the
    span edges -- a bucket that sits fully inside the span is ``partial=False``.
    """

    size: str
    index: int
    period_start: date
    period_end: date
    start_date: date
    end_date: date
    label: str
    partial: bool

    def as_dict(self) -> dict:
        return {
            "size": self.size,
            "index": self.index,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "label": self.label,
            "partial": self.partial,
        }


# ---------------------------------------------------------------------------
# Anchor capture (derives D from the caller's complete/eligible candidates -- never from "now").
# ---------------------------------------------------------------------------
def capture_anchor(
    candidates: Iterable[object] | None,
    *,
    timezone: str = "Asia/Singapore",
    date_key: str = "event_date",
    complete_key: str = "complete",
    eligible_key: str = "eligible",
    provenance: str | None = None,
) -> Anchor | None:
    """Derive the anchor ``D`` from the latest *complete, eligible* candidate the caller supplies, else ``None``.

    ``candidates`` may be a bare iterable of ``date``/``datetime`` values (each taken as complete and eligible)
    or an iterable of :class:`~typing.Mapping` records; for records the date is read from ``date_key`` and a
    record is counted only when both ``complete_key`` and ``eligible_key`` are truthy (a missing flag defaults to
    complete/eligible so a plain date-bearing record still qualifies). The anchor is the maximum qualifying
    date. When there is nothing to anchor on -- an empty iterable, or every record incomplete / ineligible -- the
    result is ``None``: **never** a fabricated date and **never** the wall clock. An incomplete row with a newer
    date therefore cannot advance ``D`` because it is simply not eligible.
    """
    if candidates is None:
        return None
    if not isinstance(candidates, Iterable) or isinstance(candidates, (str, bytes)):
        raise InvalidAnchorError("candidates must be an iterable of dates or mapping records")

    best: date | None = None
    for item in candidates:
        if isinstance(item, Mapping):
            if complete_key in item and not item[complete_key]:
                continue
            if eligible_key in item and not item[eligible_key]:
                continue
            raw = item.get(date_key)
            if raw is None:
                continue
            candidate = _coerce_date(raw, error=InvalidAnchorError, what=f"record {date_key!r}")
        else:
            candidate = _coerce_date(item, error=InvalidAnchorError, what="candidate date")
        if best is None or candidate > best:
            best = candidate

    if best is None:
        return None
    return Anchor(date=best, timezone=timezone, provenance=provenance)


# ---------------------------------------------------------------------------
# Window resolution
# ---------------------------------------------------------------------------
def resolve_relative_window(
    token: str,
    *,
    anchor: object,
    timezone: str,
) -> ResolvedWindow:
    """Resolve a relative token (``D``/``W``/``M``/``Y`` with optional ``-n``) against the captured ``anchor``.

    The window is inclusive at both ends and *always* ends at the anchor; the start follows the fixed calendar
    rules in :func:`_relative_start_date`. It never consults the wall clock. A ``None`` anchor is a
    :class:`MissingAnchorError`, an unparseable token an :class:`InvalidWindowError`, and a bad ``-n`` an
    :class:`InvalidOffsetError`.
    """
    captured = _coerce_anchor(anchor)
    _tzinfo(timezone)  # validate the project zone eagerly so a bad name fails before any arithmetic.
    base, _offset = _normalise_token(token)  # also validates the token shape and offset.
    start = _relative_start_date(token, captured)
    return ResolvedWindow(
        start_date=start,
        end_date=captured,
        anchor=captured,
        timezone=timezone,
        token=f"{base}" if _offset == 0 else f"{base}-{_offset}",
        explicit=False,
    )


def resolve_window(
    *,
    anchor: object,
    timezone: str,
    relative: str | None = None,
    start: object = None,
    end: object = None,
    subgroup_latest_eligible_date: object = None,
) -> ResolvedWindow:
    """Resolve a widget window from a relative expression *or* explicit ISO overrides against the captured anchor.

    Exactly one of ``relative`` / ``start`` names the window start. ``end`` may be omitted (defaults to the
    anchor), the literal ``"D"`` (the anchor), or an explicit ISO date literal.

    * A **relative** start always ends at the anchor and may not be paired with a non-anchor end (the "no mixed
      relative end other than D" contract) -- violating that is an :class:`InvalidWindowError`.
    * An **explicit** start is returned verbatim together with its explicit end; it is never shifted, clamped or
      truncated toward the anchor even when it names a future date. ``end >= start`` is required; a reversed
      range is an :class:`InvalidWindowError`` and a malformed / impossible ISO literal an
      :class:`InvalidDateLiteralError` (rejected by constructing a real :class:`datetime.date`).

    ``subgroup_latest_eligible_date`` is stored on the result for an informational coverage note; it never
    relocates the resolved window.
    """
    captured = _coerce_anchor(anchor)
    _tzinfo(timezone)

    if relative is not None and start is not None:
        raise InvalidWindowError("a window may not combine a relative start with an explicit start")

    # Resolve the end first: omitted / "D" -> the anchor; otherwise an explicit ISO literal kept verbatim.
    end_provided = end is not None
    if not end_provided or _is_anchor_token(end):
        end_date = captured
    else:
        end_date = parse_date_literal(end, what="window end")

    subgroup = None
    if subgroup_latest_eligible_date is not None:
        subgroup = parse_date_literal(subgroup_latest_eligible_date, what="subgroup latest eligible date")

    if relative is not None:
        base, offset = _normalise_token(relative)
        if end_provided and not _is_anchor_token(end):
            raise InvalidWindowError(
                "a relative window start may only be combined with the 'D' end token (no mixed relative end other than D)"
            )
        start_date = _relative_start_date(relative, captured)
        token = base if offset == 0 else f"{base}-{offset}"
        explicit = False
    elif start is not None:
        start_date = parse_date_literal(start, what="window start")
        token = None
        explicit = True
    else:
        raise InvalidWindowError("a window requires either a relative token or an explicit start")

    if end_date < start_date:
        raise InvalidWindowError(
            f"reversed window: start {start_date.isoformat()} is after end {end_date.isoformat()}"
        )

    return ResolvedWindow(
        start_date=start_date,
        end_date=end_date,
        anchor=captured,
        timezone=timezone,
        token=token,
        explicit=explicit,
        subgroup_latest_eligible_date=subgroup,
    )


def resolve_request(
    user_request: Mapping[str, Any],
    *,
    captured_anchor: object,
    timezone: str | None = None,
    subgroup_latest_eligible_date: object = None,
) -> ResolvedWindow:
    """Resolve a reader's window request against an *already captured* anchor; reader anchor fields are ignored.

    ``user_request`` may carry ``relative`` / ``start`` / ``end`` (interpreted through :func:`resolve_window`)
    and optionally ``subgroup_latest_eligible_date``. Any attempt to submit or move the anchor -- keys named
    ``anchor`` / ``captured_anchor`` / ``D`` / ``as_of`` -- is **dropped before resolution** and can never
    influence the result: resolution consumes only ``captured_anchor``. The captured anchor may be an
    :class:`Anchor` (its zone is then used unless ``timezone`` overrides it) or a bare ``date``/``datetime``
    (then ``timezone`` is required). A subgroup narrowing is reported as the ``subgroup_latest_eligible_date`` /
    ``coverage_note`` coverage values only -- it never relocates the resolved window.
    """
    if not isinstance(user_request, Mapping):
        raise TypeError(f"user_request must be a Mapping, got {type(user_request).__name__}")

    if isinstance(captured_anchor, Anchor):
        captured = captured_anchor.date
        zone = timezone if timezone is not None else captured_anchor.timezone
    else:
        captured = _coerce_anchor(captured_anchor)
        if timezone is None:
            raise InvalidTimezoneError("a bare-date captured_anchor requires an explicit project timezone")
        zone = timezone

    # Drop every reader-supplied anchor/D/as_of key -- the anchor is server-owned and cannot be moved by a request.
    cleaned = {key: value for key, value in user_request.items() if str(key).strip().lower() not in _FORBIDDEN_REQUEST_KEYS}

    subgroup = subgroup_latest_eligible_date
    if subgroup is None:
        for key in ("subgroup_latest_eligible_date", "subgroup_latest_eligible_date"):
            if key in cleaned:
                subgroup = cleaned[key]
                break

    return resolve_window(
        anchor=captured,
        timezone=zone,
        relative=cleaned.get("relative"),
        start=cleaned.get("start"),
        end=cleaned.get("end"),
        subgroup_latest_eligible_date=subgroup,
    )


# ---------------------------------------------------------------------------
# Query boundaries (produced without importing the ORM)
# ---------------------------------------------------------------------------
def localise_day_start(d: object, *, timezone: str) -> datetime:
    """Aware ``00:00:00`` on ``d`` in the project zone (used to build and to test the inclusive lower bound)."""
    normalised = _coerce_date(d, error=InvalidWindowError, what="date")
    return datetime.combine(normalised, time(0, 0, 0), tzinfo=_tzinfo(timezone))


def localise_day_end(d: object, *, timezone: str) -> datetime:
    """Aware ``23:59:59.999999`` on ``d`` in the project zone (the inclusive upper bound of a day)."""
    normalised = _coerce_date(d, error=InvalidWindowError, what="date")
    return datetime.combine(normalised, time(23, 59, 59, 999_999), tzinfo=_tzinfo(timezone))


def resolve_query_boundaries(
    window: ResolvedWindow,
    *,
    timezone: str | None = None,
) -> QueryBoundaries:
    """Project a resolved window into timezone-aware, inclusive ORM range instants.

    ``query_start`` is local midnight on ``window.start_date`` and ``query_end`` is local
    ``23:59:59.999999`` on ``window.end_date``, both in the project zone (``window.timezone`` unless
    ``timezone`` overrides it). No ORM is imported: the module merely emits the two aware datetimes a later
    adapter binds to a range predicate.
    """
    if not isinstance(window, ResolvedWindow):
        raise InvalidWindowError("resolve_query_boundaries expects a ResolvedWindow")
    zone = timezone if timezone is not None else window.timezone
    return QueryBoundaries(
        start_date=window.start_date,
        end_date=window.end_date,
        timezone=zone,
        query_start=localise_day_start(window.start_date, timezone=zone),
        query_end=localise_day_end(window.end_date, timezone=zone),
    )


# ---------------------------------------------------------------------------
# Bucketing (independent of the resolved relative window)
# ---------------------------------------------------------------------------
def bucket_range(
    *,
    start_date: object,
    end_date: object,
    size: str,
    timezone: str = "UTC",
) -> tuple[Bucket, ...]:
    """Bucket the inclusive span ``[start_date, end_date]`` by ``size`` -- independent of any resolved window.

    The bucket sequence is driven **only** by the span and the bucket size; it never consults the anchor or a
    resolved relative window. ``day`` yields one bucket per date; ``week`` yields Monday-start periods; ``month``
    yields calendar months; ``year`` yields calendar years. Each bucket's ``period_start`` / ``period_end`` are
    the natural calendar boundaries and its ``start_date`` / ``end_date`` the clip to the span; ``partial`` is
    ``True`` exactly when the natural period is cut by a span edge. An unknown ``size`` is an
    :class:`UnknownBucketError` and a reversed span an :class:`InvalidWindowError`.
    """
    start = _coerce_date(start_date, error=InvalidWindowError, what="bucket span start")
    end = _coerce_date(end_date, error=InvalidWindowError, what="bucket span end")
    if end < start:
        raise InvalidWindowError(
            f"reversed bucket span: start {start.isoformat()} is after end {end.isoformat()}"
        )
    if not isinstance(size, str) or size.strip().lower() not in BUCKET_SIZES:
        raise UnknownBucketError(f"unknown bucket size {size!r}; expected one of {sorted(BUCKET_SIZES)}")
    size = size.strip().lower()
    _tzinfo(timezone)  # the zone is validated so a rendered/aware bucket boundary is always meaningful.

    buckets: list[Bucket] = []

    def _emit(index: int, period_start: date, period_end: date) -> None:
        clip_start = max(start, period_start)
        clip_end = min(end, period_end)
        if clip_end < clip_start:
            return
        partial = period_start < start or period_end > end
        buckets.append(
            Bucket(
                size=size,
                index=index,
                period_start=period_start,
                period_end=period_end,
                start_date=clip_start,
                end_date=clip_end,
                label=f"{period_start.isoformat()}/{period_end.isoformat()}",
                partial=partial,
            )
        )

    if size == "day":
        cursor = start
        index = 0
        while cursor <= end:
            _emit(index, cursor, cursor)
            cursor = cursor + timedelta(days=1)
            index += 1
        return tuple(buckets)

    if size == "week":
        cursor = _week_start(start)
        index = 0
        while cursor <= end:
            _emit(index, cursor, cursor + timedelta(days=6))
            cursor = cursor + timedelta(days=7)
            index += 1
        return tuple(buckets)

    if size == "month":
        cursor = _month_start(start)
        index = 0
        while cursor <= end:
            _emit(index, cursor, _month_end(cursor))
            cursor = _shift_months(cursor, -1)
            index += 1
        return tuple(buckets)

    # size == "year"
    year = start.year
    index = 0
    while date(year, 1, 1) <= end:
        _emit(index, date(year, 1, 1), date(year, 12, 31))
        year += 1
        index += 1
    return tuple(buckets)

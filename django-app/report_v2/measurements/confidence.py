# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Per-proportion confidence intervals (Wilson) + an explicit CI method registry.

Only an explicitly registered (metric, method) pair may publish a CI; anything else —
unknown metric, unknown method string, or balanced-accuracy with any CI — is rejected with
a typed UnsupportedCiError *before* publication. Balanced accuracy is a (sens+spec)/2
average, not a proportion, so it has no per-proportion CI and must never be defaulted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

# 95% two-sided default z = 1.959963984540054
DEFAULT_Z = 1.959963984540054


class ConfidenceError(Exception):
    """Base class for confidence-interval errors."""


class OutOfRangeCountError(ConfidenceError):
    """Raised when k is not in [0, n] (the input is never clamped)."""


class UnsupportedCiError(ConfidenceError):
    """Raised when a (metric, method) pair was never registered."""


@dataclass(frozen=True)
class WilsonInterval:
    """A Wilson score interval, or a null value carrying a ``null_reason``."""

    k: int
    n: int
    lower: float | None
    upper: float | None
    confidence_level: float = 0.95
    method: str = "wilson"
    available: bool = True
    null_reason: str | None = None


def wilson_interval(k: int, n: int, *, z: float = DEFAULT_Z) -> WilsonInterval:
    """Return the 95% two-sided Wilson score interval for ``k`` successes in ``n`` trials.

    The 95% two-sided default ``z`` is ``1.959963984540054``.

    Rules:
      * ``n <= 0``     -> unavailable, bounds ``None`` with a ``null_reason`` (never [0, 0]).
      * ``k < 0``/``k > n`` -> raise :class:`OutOfRangeCountError` (input never clamped).
      * only the *result* is clamped into ``[0, 1]``.
    """
    if n <= 0:
        return WilsonInterval(
            k=k, n=n, lower=None, upper=None,
            available=False, null_reason="n must be > 0",
        )
    if k < 0 or k > n:
        raise OutOfRangeCountError(f"k={k} out of range for n={n} (must satisfy 0 <= k <= n)")

    p = k / n
    z2 = z * z
    d = 1 + z2 / n
    center = (p + z2 / (2 * n)) / d
    half = z / d * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    lower = max(0.0, center - half)
    upper = min(1.0, center + half)
    return WilsonInterval(k=k, n=n, lower=lower, upper=upper)


# ponytail: registry stores plain (metric, method) tuples; no CI computation is implied here.
_registered_cis: set[tuple[str, str]] = set()

#: Identity spellings of the ``(sensitivity + specificity) / 2`` average. It is a mean of two
#: recall-style rates, NOT a proportion, so it has no per-proportion CI and can never be
#: registered or defaulted -- requesting any CI for it is a hard ``UnsupportedCiError``.
BALANCED_ACCURACY_IDENTITIES = frozenset(
    {"balanced_accuracy", "balanced accuracy", "balancedaccuracy", "balanced_acc"}
)


def _is_balanced_accuracy(metric_name: str) -> bool:
    return str(metric_name).strip().casefold().replace("-", "_") in BALANCED_ACCURACY_IDENTITIES


def register_proportion_ci(metric_name: str, method: str = "wilson") -> None:
    """Allow ``method`` to be requested for the proportion ``metric_name``.

    Balanced accuracy is a ``(sens + spec) / 2`` average, not a proportion, so it is refused
    here rather than silently registered -- its CI can never be invented through this door.
    """
    if _is_balanced_accuracy(metric_name):
        raise UnsupportedCiError(
            f"balanced accuracy is not a proportion; no CI may be registered for it "
            f"(method={method!r})"
        )
    _registered_cis.add((metric_name, method))


def is_proportion_ci_registered(metric_name: str, method: str = "wilson") -> bool:
    return (metric_name, method) in _registered_cis


def require_proportion_ci(metric_name: str, method: str = "wilson") -> Callable[..., object]:
    """Resolve a registered CI for ``method`` or raise :class:`UnsupportedCiError`.

    Unregistered (metric, method) pairs — including balanced_accuracy with any CI — fail here,
    before publication. Callers may instead simply omit the unsupported CI column entirely.
    """
    if (metric_name, method) not in _registered_cis:
        raise UnsupportedCiError(
            f"CI method {method!r} is not registered for metric {metric_name!r}"
        )
    return wilson_interval


__all__ = [
    "WilsonInterval",
    "wilson_interval",
    "ConfidenceError",
    "OutOfRangeCountError",
    "UnsupportedCiError",
    "register_proportion_ci",
    "is_proportion_ci_registered",
    "require_proportion_ci",
    "DEFAULT_Z",
]

# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Strict, side-effect-free parser + structural schema validation for report v2 definitions.

This module is the gatekeeper for the report-v2 authoring pipeline. It turns an author-supplied
YAML *string* into a plain Python value, rejects every construct the YAML contract forbids
(anchors, aliases, merge keys, unknown tags, multiple documents, duplicate keys, oversized or
unbounded input, non-finite numbers and impossible calendar dates), and validates the resulting
structure against the packaged JSON Schemas.

Design rules that the rest of the system relies on:

* Never touches disk during validation: the only reads are the packaged ``*.schema.json`` files,
  opened in read mode once and then kept in an in-process cache. Nothing is ever written out.
* Never interprets author strings as programs or as interpolation placeholders. A value such as
  ``"{__class__.__init__}"`` or ``"{{ 7*7 }}"`` is returned verbatim as a plain ``str``.
* Every rejection is a typed :class:`DefinitionError` subclass carrying an editor-friendly message
  plus, where knowable, a dotted/bracketed ``path``, a 1-based ``line``, a 1-based ``column`` and
  the ``source`` label, so an editor can highlight the offending node.

The strict loader subclasses :class:`yaml.SafeLoader` and drives it through the composer hooks so
that anchors/aliases/tags/duplication/size are refused during composition -- before any object is
built. Document boundaries and scanner/parser failures are mapped around the single-document entry
point. The schema layer uses ``jsonschema.Draft202012Validator``.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from jsonschema import Draft202012Validator
from yaml.composer import ComposerError
from yaml.constructor import ConstructorError, SafeConstructor as _SafeConstructor
from yaml.error import MarkedYAMLError
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, ScalarNode, SequenceNode
from yaml.parser import ParserError
from yaml.scanner import ScannerError

# ---------------------------------------------------------------------------
# Tag allow-lists (the only tags a strict document may resolve to).
# ---------------------------------------------------------------------------
SAFE_IMPLICIT = {
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:value",
    "tag:yaml.org,2002:timestamp",
    "tag:yaml.org,2002:str",
}
SAFE_EXPLICIT = {
    "tag:yaml.org,2002:seq",
    "tag:yaml.org,2002:map",
    "tag:yaml.org,2002:str",
}
ALLOWED_TAGS = SAFE_IMPLICIT | SAFE_EXPLICIT
MERGE_TAG = "tag:yaml.org,2002:merge"
TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"
FLOAT_TAG = "tag:yaml.org,2002:float"
INT_TAG = "tag:yaml.org,2002:int"
STR_TAG = "tag:yaml.org,2002:str"
VALUE_TAG = "tag:yaml.org,2002:value"

# Literals PyYAML's float constructor turns into non-finite floats.
_NONFINITE_LITERALS = {".inf", "-.inf", "+.inf", "inf", "-inf", "+inf", ".nan", "-.nan", "+.nan", "nan", "-nan", "+nan"}

# ISO calendar date shape used by the semantic date gate (NOT the sole reason a bad date is refused).
_DATE_SHAPE = r"^\d{4}-\d{2}-\d{2}$"

# Relative window tokens are never date-checked: D/W/M/Y and the D-n / W-n / M-n / Y-n forms.
_RELATIVE_TOKEN = r"^[DWMY](-\d+)?$"


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------
class DefinitionError(Exception):
    """Common base for every rejection produced by the definition pipeline.

    Carries the fields an editor needs: a human ``message`` and, when knowable, a dotted/bracketed
    ``path``, a 1-based ``line``, a 1-based ``column`` and the ``source`` label. ``kind`` is a stable
    machine-readable discriminator; subclasses override it.
    """

    kind = "definition-error"

    def __init__(self, message, *, path=None, line=None, column=None, source=None):
        self.message = str(message)
        self.path = path
        self.line = line
        self.column = column
        self.source = source
        super().__init__(self.message)

    def as_editor_dict(self):
        """Return a JSON-friendly mapping an editor/IDE can render directly."""
        return {
            "source": self.source,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "kind": self.kind,
            "message": self.message,
        }

    def __str__(self):
        loc = []
        if self.source:
            loc.append(str(self.source))
        if self.path:
            loc.append(str(self.path))
        if self.line is not None:
            if self.column is not None:
                loc.append(f"{self.line}:{self.column}")
            else:
                loc.append(str(self.line))
        prefix = f"[{self.kind}]"
        where = (" " + ":".join(loc)) if loc else ""
        return f"{prefix}{where} {self.message}"


class YamlSyntaxError(DefinitionError):
    kind = "yaml-syntax"


class DuplicateKeyError(DefinitionError):
    kind = "duplicate-key"


class AnchorAliasError(DefinitionError):
    kind = "anchor-or-alias"


class MergeKeyError(DefinitionError):
    kind = "merge-key"


class UnknownTagError(DefinitionError):
    kind = "unknown-tag"


class MultipleDocumentsError(DefinitionError):
    kind = "multiple-documents"


class SizeLimitError(DefinitionError):
    kind = "size-limit"


class DepthLimitError(DefinitionError):
    kind = "depth-limit"


class NodeCountLimitError(DefinitionError):
    kind = "node-count-limit"


class ScalarSizeLimitError(DefinitionError):
    kind = "scalar-size-limit"


class NonFiniteNumberError(DefinitionError):
    kind = "non-finite-number"


class InvalidCalendarDateError(DefinitionError):
    kind = "invalid-calendar-date"


class SchemaValidationError(DefinitionError):
    kind = "schema-validation"

    def __init__(self, message, *, path=None, line=None, column=None, source=None, errors=None):
        super().__init__(message, path=path, line=line, column=column, source=source)
        # ``errors`` is the full deterministic list of ``as_editor_dict`` mappings when this error is
        # raised as an aggregate of every schema violation found in one document.
        self.errors = list(errors) if errors else [self.as_editor_dict()]


# Every error the pipeline raises itself (as opposed to a framework error mapped in ``_parse_once``).
# These are NOT :class:`MarkedYAMLError` subclasses so they traverse the framework ``except`` clauses
# untouched.
_PIPELINE_ERRORS = (
    DefinitionError,
)


def _mark_location(exc):
    """Best-effort 1-based (line, column) from a PyYAML MarkedYAMLError."""
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    if mark is None:
        return None, None
    line = None if getattr(mark, "line", None) is None else int(mark.line) + 1
    column = None if getattr(mark, "column", None) is None else int(mark.column) + 1
    return line, column


def _describe_marked(exc):
    line, column = _mark_location(exc)
    reason = getattr(exc, "problem", None) or getattr(exc, "context", None) or str(exc)
    reason = str(reason).split("\n")[0]
    return reason, line, column


# ---------------------------------------------------------------------------
# The strict loader
# ---------------------------------------------------------------------------
class StrictLoader(yaml.SafeLoader):
    """A :class:`yaml.SafeLoader` that refuses every construct outside the YAML contract.

    Limits are keyword-only and ``None`` means "unbounded" for that axis. ``nonfinite_ok`` relaxes the
    ``.nan`` / ``.inf`` rejection (never used by the report/policy loaders, which require finite data).
    """

    def __init__(self, stream, *, max_bytes=None, max_nodes=None, max_str=None, max_depth=None, nonfinite_ok=False):
        self._max_nodes = max_nodes
        self._max_str = max_str
        self._max_depth = max_depth
        self._nonfinite_ok = bool(nonfinite_ok)
        self._node_count = 0
        self._depth = 0
        self._path_stack = [""]
        # ``SafeLoader.__init__`` does not forward extra kwargs to the mixins, so limits live only on self.
        super().__init__(stream)

    # -- helpers ------------------------------------------------------------
    def _err(self, exc_type, message, node=None, mark_owner=None, path=None):
        if path is None:
            path = getattr(node, "_path", None) if node is not None else (self._path_stack[-1] or None)
        line = column = None
        mark = None
        if node is not None:
            mark = getattr(node, "start_mark", None)
        if mark is not None:
            line = None if mark.line is None else int(mark.line) + 1
            column = None if mark.column is None else int(mark.column) + 1
        return exc_type(message, path=path, line=line, column=column, source=self._source)

    def _child_path(self, parent, index):
        parent_path = self._path_stack[-1]
        joiner = "." if parent_path else ""
        if parent is None:
            return ""
        if isinstance(parent, SequenceNode):
            return f"{parent_path}[{index}]"
        if isinstance(parent, MappingNode):
            if index is None:
                return f"{parent_path}{joiner}<key>"
            if isinstance(index, ScalarNode):
                return f"{parent_path}{joiner}{index.value}"
            return f"{parent_path}[complex-key]"
        return parent_path

    # -- composition hooks --------------------------------------------------
    def compose_node(self, parent, index):
        peek = self.peek_event()

        # Alias / anchor rejection is decided from parser events (nodes do not reliably carry .anchor).
        if isinstance(peek, AliasEvent):
            raise self._err(AnchorAliasError, "aliases ( '*name' ) are not allowed")
        if getattr(peek, "anchor", None):
            raise self._err(AnchorAliasError, "anchors ( '&name' ) are not allowed")

        # Unknown explicit tag (e.g. '!foo' or '!!binary'); implicit nodes report tag None and are
        # resolved afterwards against the same allow-list below.
        peek_tag = getattr(peek, "tag", None)
        if peek_tag is not None and peek_tag not in ALLOWED_TAGS:
            raise self._err(UnknownTagError, f"unknown tag {peek_tag!r} is not permitted")

        child_path = self._child_path(parent, index)
        self._path_stack.append(child_path)
        self._depth += 1
        self._node_count += 1
        try:
            if self._max_depth is not None and self._depth > self._max_depth:
                raise self._err(
                    DepthLimitError,
                    f"nesting depth {self._depth} exceeds the maximum of {self._max_depth}",
                )
            if self._max_nodes is not None and self._node_count > self._max_nodes:
                raise self._err(
                    NodeCountLimitError,
                    f"node count {self._node_count} exceeds the maximum of {self._max_nodes}",
                )

            node = super().compose_node(parent, index)

            # Collection/scalar tags produced by the composer must land inside the allow-list. The merge
            # tag is intentionally exempt here so compose_mapping_node can raise the dedicated merge error.
            if node.tag == MERGE_TAG or (isinstance(node, ScalarNode) and node.value == "<<"):
                if isinstance(parent, MappingNode) and index is None:
                    raise self._err(MergeKeyError, "merge keys ( '<<' ) are not allowed", node=node)
            if node.tag not in ALLOWED_TAGS and node.tag != MERGE_TAG:
                raise self._err(UnknownTagError, f"tag {node.tag!r} resolved to a non-permitted tag", node=node)

            if isinstance(node, ScalarNode):
                if self._max_str is not None and node.tag == STR_TAG and len(node.value) > self._max_str:
                    raise self._err(
                        ScalarSizeLimitError,
                        f"scalar length {len(node.value)} exceeds the maximum of {self._max_str}",
                        node=node,
                    )
                if not self._nonfinite_ok and node.tag == FLOAT_TAG:
                    if self._is_nonfinite(node.value):
                        raise self._err(
                            NonFiniteNumberError,
                            f"non-finite number {node.value!r} is not allowed",
                            node=node,
                        )
        finally:
            self._depth -= 1
            self._path_stack.pop()

        node._path = child_path
        return node

    def compose_mapping_node(self, anchor):
        if anchor:
            raise self._err(AnchorAliasError, "anchors ( '&name' ) are not allowed")
        node = super().compose_mapping_node(anchor=anchor)

        seen = {}
        for key_node, _value_node in node.value:
            if key_node.tag == MERGE_TAG or (isinstance(key_node, ScalarNode) and key_node.value == "<<"):
                raise self._err(MergeKeyError, "merge keys ( '<<' ) are not allowed", node=key_node)
            ident = (key_node.tag, getattr(key_node, "value", None))
            if ident in seen:
                parent_path = self._path_stack[-1]
                joiner = "." if parent_path else ""
                key_repr = getattr(key_node, "value", "?")
                raise self._err(
                    DuplicateKeyError,
                    f"duplicate mapping key {key_repr!r}",
                    node=key_node,
                    path=f"{parent_path}{joiner}{key_repr}",
                )
            seen[ident] = True
        return node

    def compose_sequence_node(self, anchor):
        if anchor:
            raise self._err(AnchorAliasError, "anchors ( '&name' ) are not allowed")
        return super().compose_sequence_node(anchor=anchor)

    # -- construction hooks -------------------------------------------------
    def construct_yaml_timestamp(self, node):
        """Validate a timestamp scalar and normalise valid ones to an ISO string.

        An impossible calendar date such as ``2026-02-30`` is refused here (with the offending node's
        path/marks) rather than being allowed to raise a raw built-in ``ValueError``. Valid date-only
        scalars become ``'YYYY-MM-DD'`` strings so the structural schema (which expects ``type: string``
        for window bounds) still validates.
        """
        try:
            value = _SafeConstructor.construct_yaml_timestamp(self, node)
        except Exception as exc:  # built-in date/datetime range errors surface as ValueError
            raise self._err(
                InvalidCalendarDateError,
                f"{getattr(node, 'value', '?')!r} is not a valid calendar date",
                node=node,
            ) from exc
        if isinstance(value, _dt.datetime):
            return value.isoformat()
        if isinstance(value, _dt.date):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _is_nonfinite(text):
        if text is None:
            return False
        normalized = str(text).replace("_", "").strip().lower()
        if normalized in _NONFINITE_LITERALS:
            return True
        try:
            return not math.isfinite(float(normalized))
        except (ValueError, TypeError):
            return False


# PyYAML dispatches timestamp scalars by a stored tag->constructor mapping, so overriding the method on
# a subclass is not enough -- bind the tag to our validator/normaliser explicitly.
StrictLoader.add_constructor(TIMESTAMP_TAG, StrictLoader.construct_yaml_timestamp)


# ---------------------------------------------------------------------------
# Pure parse entry point (never writes to disk)
# ---------------------------------------------------------------------------
def _coerce_source(source):
    return None if source in (None, "") else str(source)


def parse_strict_yaml(text, *, source="<definition>", max_bytes=None, max_nodes=None, max_str=None, max_depth=None, nonfinite_ok=False):
    """Parse ``text`` strictly and return the resulting plain Python value.

    Raises a specific :class:`DefinitionError` subclass on any forbidden construct. The function is
    pure: it performs no file-system writes. ``source`` is only a label threaded into the errors.
    """
    label = _coerce_source(source)
    if isinstance(text, (bytes, bytearray)):
        decode_text = bytes(text).decode("utf-8")
    else:
        decode_text = str(text)

    if max_bytes is not None:
        size = len(decode_text.encode("utf-8"))
        if size > max_bytes:
            raise SizeLimitError(
                f"document size {size} bytes exceeds the maximum of {max_bytes} bytes",
                source=label,
                line=1,
                column=1,
            )

    loader = StrictLoader(
        decode_text,
        max_nodes=max_nodes,
        max_str=max_str,
        max_depth=max_depth,
        nonfinite_ok=nonfinite_ok,
    )
    loader._source = label
    try:
        # ``get_single_data`` enforces the single-document rule (raising ComposerError on a second doc)
        # and runs compose + construct in one pass.
        return loader.get_single_data()
    except ComposerError as exc:
        reason, line, column = _describe_marked(exc)
        if "single document" in reason or "another" in reason:
            raise MultipleDocumentsError(
                "a definition must contain exactly one YAML document; multiple documents are not allowed",
                source=label,
                line=line,
                column=column,
            ) from exc
        raise YamlSyntaxError(reason, source=label, line=line, column=column) from exc
    except (ScannerError, ParserError) as exc:
        reason, line, column = _describe_marked(exc)
        raise YamlSyntaxError(reason, source=label, line=line, column=column) from exc
    except MarkedYAMLError as exc:  # any other marked framework failure
        reason, line, column = _describe_marked(exc)
        raise YamlSyntaxError(reason, source=label, line=line, column=column) from exc
    finally:
        loader.dispose()


# ---------------------------------------------------------------------------
# Schema plumbing (read-once, cached)
# ---------------------------------------------------------------------------
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def schema_path(name):
    """Absolute path to a packaged schema JSON file (accepts bare name or ``*.schema.json``)."""
    if not str(name).endswith(".json"):
        name = f"{name}.schema.json"
    return SCHEMA_DIR / name


@lru_cache(maxsize=None)
def load_schema(name):
    """Read and cache a packaged schema JSON document once, in read-only mode."""
    path = schema_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"missing schema file: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=None)
def _report_validator():
    return Draft202012Validator(load_schema("report"))


@lru_cache(maxsize=None)
def _policy_validator():
    return Draft202012Validator(load_schema("policy"))


def _schema_path(error):
    """Derive a ``$``-rooted JSONPath-style string from a jsonschema absolute path (deque of str/int)."""
    out = ["$"]
    for part in error.absolute_path:
        if isinstance(part, int):
            out.append(f"[{part}]")
        else:
            out.append(f".{part}")
    return "".join(out)


def _schema_error_to_validation(error, label):
    return SchemaValidationError(
        error.message,
        path=_schema_path(error),
        line=None,
        column=None,
        source=label,
    )


def _iter_schema_problems(data, validator, label):
    problems = []
    for error in validator.iter_errors(data):
        problems.append(_schema_error_to_validation(error, label))
    # Deterministic ordering: path first, then message.
    problems.sort(key=lambda err: (str(err.path or ""), str(err.message)))
    return problems


def _raise_first_schema(problems):
    if not problems:
        return None
    first = problems[0]
    raise SchemaValidationError(
        first.message,
        path=first.path,
        line=first.line,
        column=first.column,
        source=first.source,
        errors=[problem.as_editor_dict() for problem in problems],
    )


def validate_against_report_schema(data, *, source="<report-definition>"):
    """Return the deterministic list of :class:`SchemaValidationError` for ``data`` (empty == valid)."""
    label = _coerce_source(source)
    return _iter_schema_problems(data, _report_validator(), label)


def validate_against_policy_schema(data, *, source="<policy>"):
    """Return the deterministic list of :class:`SchemaValidationError` for ``data`` (empty == valid)."""
    label = _coerce_source(source)
    return _iter_schema_problems(data, _policy_validator(), label)


# ---------------------------------------------------------------------------
# Semantic calendar-date gate (structural + date semantics only)
# ---------------------------------------------------------------------------
def _walk_dates(node, path, label, sink):
    if isinstance(node, dict):
        for key, value in node.items():
            joiner = "." if path else ""
            child = f"{path}{joiner}{key}" if isinstance(key, str) else f"{path}[{key}]"
            _walk_dates(value, child, label, sink)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _walk_dates(value, f"{path}[{index}]", label, sink)
    elif isinstance(node, str):
        # Relative window tokens are never dates; only the YYYY-MM-DD shape is calendar-checked.
        if re.match(_RELATIVE_TOKEN, node):
            return
        if re.match(_DATE_SHAPE, node):
            year, month, day = int(node[0:4]), int(node[5:7]), int(node[8:10])
            try:
                _dt.date(year, month, day)
            except Exception:
                sink.append(
                    InvalidCalendarDateError(
                        f"{node!r} at {path or '$'} is not a valid calendar date",
                        path=path or None,
                        line=None,
                        column=None,
                        source=label,
                    )
                )


def validate_calendar_dates(data, *, source="<definition>"):
    """Collect :class:`InvalidCalendarDateError` for every impossible ``YYYY-MM-DD`` string in ``data``.

    The check is genuinely semantic: a value can match the shape regex yet still name a day that never
    existed (e.g. ``2026-02-30``) and is refused because ``datetime.date`` rejects it. Relative window
    tokens (``D``/``W``/``M``/``Y`` and the ``-n`` forms) are never date-checked.
    """
    label = _coerce_source(source)
    errors = []
    _walk_dates(data, "", label, errors)
    return errors


# ---------------------------------------------------------------------------
# Light semantic policy checks (shape/bounds already implied by the seed)
# ---------------------------------------------------------------------------
def _is_finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _semantic_policy_problems(data, label):
    problems = []

    scale = data.get("score_scale")
    if isinstance(scale, list) and len(scale) == 2:
        low, high = scale[0], scale[1]
        if not (_is_finite_number(low) and _is_finite_number(high) and low < high):
            problems.append(
                SchemaValidationError(
                    "score_scale must be [lo, hi] with finite lo < hi",
                    path="$.score_scale",
                    source=label,
                )
            )

    findings = data.get("findings")
    if isinstance(findings, dict) and isinstance(scale, list) and len(scale) == 2:
        low, high = scale[0], scale[1]
        if _is_finite_number(low) and _is_finite_number(high):
            for key, value in findings.items():
                if not _is_finite_number(value):
                    problems.append(
                        SchemaValidationError(
                            f"finding threshold {value!r} is not finite",
                            path=f"$.findings.{key}",
                            source=label,
                        )
                    )
                elif not (low <= value <= high):
                    problems.append(
                        SchemaValidationError(
                            f"finding threshold {value!r} is outside the score scale [{low}, {high}]",
                            path=f"$.findings.{key}",
                            source=label,
                        )
                    )
    problems.sort(key=lambda err: (str(err.path or ""), str(err.message)))
    return problems


# ---------------------------------------------------------------------------
# Load-and-validate entry points
# ---------------------------------------------------------------------------
def load_report_definition(text, *, source="<report-definition>", **limits):
    """Parse a report definition string, validate it structurally and semantically, return the dict.

    Raises on the first failure; a :class:`SchemaValidationError` raised for schema problems carries the
    full deterministic ``errors`` list. Pure: never writes to disk.
    """
    data = parse_strict_yaml(text, source=source, **limits)
    problems = validate_against_report_schema(data, source=source)
    if problems:
        _raise_first_schema(problems)
    date_problems = validate_calendar_dates(data, source=source)
    if date_problems:
        raise date_problems[0]
    return data


def load_policy(text, *, source="<policy>", **limits):
    """Parse a threshold-policy definition string, validate it, return the dict (never writing to disk)."""
    data = parse_strict_yaml(text, source=source, **limits)
    problems = validate_against_policy_schema(data, source=source)
    if problems:
        _raise_first_schema(problems)
    semantic = _semantic_policy_problems(data, _coerce_source(source))
    if semantic:
        _raise_first_schema(semantic)
    date_problems = validate_calendar_dates(data, source=source)
    if date_problems:
        raise date_problems[0]
    return data


def prewarm_schemas():
    """Populate the schema/validator caches without touching the network or disk for validation again."""
    _report_validator()
    _policy_validator()


__all__ = [
    "DefinitionError",
    "YamlSyntaxError",
    "DuplicateKeyError",
    "AnchorAliasError",
    "MergeKeyError",
    "UnknownTagError",
    "MultipleDocumentsError",
    "SizeLimitError",
    "DepthLimitError",
    "NodeCountLimitError",
    "ScalarSizeLimitError",
    "NonFiniteNumberError",
    "InvalidCalendarDateError",
    "SchemaValidationError",
    "StrictLoader",
    "parse_strict_yaml",
    "validate_against_report_schema",
    "validate_against_policy_schema",
    "validate_calendar_dates",
    "load_report_definition",
    "load_policy",
    "SCHEMA_DIR",
    "schema_path",
    "load_schema",
    "prewarm_schemas",
]

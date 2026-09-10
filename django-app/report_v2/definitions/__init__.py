# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Report-v2 definition authoring primitives (strict YAML + structural schemas).

The heavy lifting lives in :mod:`report_v2.definitions.loader`; this package marker re-exports the
public surface so callers can ``from report_v2.definitions import load_report_definition`` directly.
"""

from __future__ import annotations

from .loader import (
    AnchorAliasError,
    DefinitionError,
    DepthLimitError,
    DuplicateKeyError,
    InvalidCalendarDateError,
    MergeKeyError,
    MultipleDocumentsError,
    NodeCountLimitError,
    NonFiniteNumberError,
    ScalarSizeLimitError,
    SchemaValidationError,
    SCHEMA_DIR,
    SizeLimitError,
    StrictLoader,
    UnknownTagError,
    YamlSyntaxError,
    load_policy,
    load_report_definition,
    load_schema,
    parse_strict_yaml,
    prewarm_schemas,
    schema_path,
    validate_against_policy_schema,
    validate_against_report_schema,
    validate_calendar_dates,
)

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

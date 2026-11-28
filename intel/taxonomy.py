"""Load and check the scam-type list (intel/taxonomy.yaml).

Everything that needs the list of scam types (the classifier, the labelling file's dropdown,
the FTC / IC3 matching, the simulator) reads it through `load_taxonomy()`, so they can never
drift apart. The loader refuses an incomplete file instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

TAXONOMY_FILE = Path(__file__).with_name("taxonomy.yaml")
MATCHES = ("exact", "part", "none")
_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class TaxonomyError(ValueError):
    """The taxonomy file is incomplete or inconsistent."""


@dataclass(frozen=True)
class ReportMapping:
    """One link from our type to a category in an outside report (FTC or IC3)."""

    category: str
    subcategory: str | None
    match: str


@dataclass(frozen=True)
class ScamType:
    id: str
    name: str
    definition: str
    authorised_payment: bool
    in_simulator: bool
    ftc: tuple[ReportMapping, ...]
    ic3: tuple[ReportMapping, ...]
    note: str | None


@dataclass(frozen=True)
class WorkedExample:
    """A short made-up story showing how a tie-break rule is applied."""

    story: str
    label: str
    why: str


@dataclass(frozen=True)
class TieBreak:
    rule: str
    examples: tuple[WorkedExample, ...]


@dataclass(frozen=True)
class Flag:
    """A yes/no question recorded alongside the scam type (not a type itself)."""

    id: str
    question: str
    definition: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class Taxonomy:
    version: int
    date: date
    verified_against_reports: bool
    types: tuple[ScamType, ...]
    tie_breaks: tuple[TieBreak, ...]
    flags: tuple[Flag, ...]

    @property
    def ids(self) -> tuple[str, ...]:
        """The label choices, in file order (used for the labelling dropdown)."""
        return tuple(t.id for t in self.types)

    def flag(self, flag_id: str) -> Flag:
        for f in self.flags:
            if f.id == flag_id:
                return f
        raise KeyError(f"unknown flag {flag_id!r}")

    def get(self, type_id: str) -> ScamType:
        for t in self.types:
            if t.id == type_id:
                return t
        raise KeyError(f"unknown scam type {type_id!r}; known: {', '.join(self.ids)}")


def load_taxonomy(path: Path = TAXONOMY_FILE) -> Taxonomy:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TaxonomyError(f"{path.name} must be a YAML mapping")
    raw_types = _require(data, "types", list, "file")
    types = tuple(_scam_type(raw, i) for i, raw in enumerate(raw_types))

    ids = [t.id for t in types]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise TaxonomyError(f"duplicate scam type ids: {', '.join(duplicates)}")
    if not any(not t.authorised_payment for t in types):
        raise TaxonomyError("at least one type must be an unauthorised (non-scam) contrast case")

    raw_rules = _require(data, "tie_breaks", list, "file")
    if not raw_rules:
        raise TaxonomyError("tie_breaks must be a non-empty list of rules")
    tie_breaks = tuple(_tie_break(raw, i, set(ids)) for i, raw in enumerate(raw_rules))

    raw_flags = _require(data, "flags", list, "file")
    flags = tuple(_flag(raw, i, set(ids)) for i, raw in enumerate(raw_flags))

    return Taxonomy(
        version=_require(data, "version", int, "file"),
        date=_require(data, "date", date, "file"),
        verified_against_reports=_require(data, "verified_against_reports", bool, "file"),
        types=types,
        tie_breaks=tie_breaks,
        flags=flags,
    )


def _tie_break(raw: Any, index: int, type_ids: set[str]) -> TieBreak:
    where = f"tie-break #{index + 1}"
    if not isinstance(raw, dict):
        raise TaxonomyError(f"{where} must be a mapping with a 'rule'")
    rule = _require(raw, "rule", str, where).strip()
    if not rule:
        raise TaxonomyError(f"{where}: rule is empty")
    examples = []
    for ex in raw.get("examples", []):
        if not isinstance(ex, dict):
            raise TaxonomyError(f"{where}: each example must be a mapping")
        label = _require(ex, "label", str, where)
        if label not in type_ids:
            raise TaxonomyError(f"{where}: example label {label!r} is not a scam type id")
        story = _require(ex, "story", str, where).strip()
        why = _require(ex, "why", str, where).strip()
        if not story or not why:
            raise TaxonomyError(f"{where}: an example needs a story and a reason")
        examples.append(WorkedExample(story, label, why))
    return TieBreak(rule, tuple(examples))


def _flag(raw: Any, index: int, type_ids: set[str]) -> Flag:
    if not isinstance(raw, dict):
        raise TaxonomyError(f"flag #{index + 1} must be a mapping")
    flag_id = _require(raw, "id", str, f"flag #{index + 1}")
    where = f"flag {flag_id!r}"
    if not _ID.fullmatch(flag_id):
        raise TaxonomyError(f"{where}: id must be lower_snake_case")
    if flag_id in type_ids:
        raise TaxonomyError(f"{where}: a flag can't share its id with a scam type")
    values = _require(raw, "values", list, where)
    if values != ["yes", "no"]:
        raise TaxonomyError(f'{where}: values must be exactly ["yes", "no"] (quoted)')
    question = _require(raw, "question", str, where).strip()
    definition = _require(raw, "definition", str, where).strip()
    if not question or not definition:
        raise TaxonomyError(f"{where}: needs a question and a definition")
    return Flag(flag_id, question, definition, ("yes", "no"))


def _scam_type(raw: Any, index: int) -> ScamType:
    if not isinstance(raw, dict):
        raise TaxonomyError(f"type #{index + 1} must be a mapping")
    type_id = _require(raw, "id", str, f"type #{index + 1}")
    if not _ID.fullmatch(type_id):
        raise TaxonomyError(f"type id {type_id!r} must be lower_snake_case")
    where = f"type {type_id!r}"
    for text_field in ("name", "definition"):
        if not _require(raw, text_field, str, where).strip():
            raise TaxonomyError(f"{where}: {text_field} is empty")
    note = raw.get("note")
    return ScamType(
        id=type_id,
        name=raw["name"].strip(),
        definition=raw["definition"].strip(),
        authorised_payment=_require(raw, "authorised_payment", bool, where),
        in_simulator=_require(raw, "in_simulator", bool, where),
        ftc=_mappings(raw, "ftc", "category", where),
        ic3=_mappings(raw, "ic3", "crime_type", where),
        note=note.strip() if isinstance(note, str) else None,
    )


def _mappings(
    raw: dict[str, Any], report: str, name_key: str, where: str
) -> tuple[ReportMapping, ...]:
    entries = _require(raw, report, list, where)
    if not entries:
        raise TaxonomyError(
            f"{where}: needs at least one {report.upper()} mapping (use match: none)"
        )
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TaxonomyError(f"{where}: each {report.upper()} mapping must be a mapping")
        category = str(entry.get(name_key, "")).strip()
        match = entry.get("match")
        if not category:
            raise TaxonomyError(f"{where}: {report.upper()} mapping has no {name_key}")
        if match not in MATCHES:
            raise TaxonomyError(
                f"{where}: {report.upper()} match must be one of {MATCHES}, not {match!r}"
            )
        if (match == "none") != (category == "none"):
            raise TaxonomyError(f"{where}: use category 'none' exactly when match is 'none'")
        sub = entry.get("subcategory")
        result.append(ReportMapping(category, str(sub).strip() if sub else None, match))
    return tuple(result)


def _require(raw: dict[str, Any], key: str, kind: type, where: str) -> Any:
    if key not in raw:
        raise TaxonomyError(f"{where}: missing {key!r}")
    value = raw[key]
    # bool is a kind of int in Python; don't let `true` pass as a version number.
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise TaxonomyError(f"{where}: {key!r} must be {kind.__name__}, not {type(value).__name__}")
    return value

"""The scam-type list must be complete, consistent, and include Martins' required types."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from intel.taxonomy import TAXONOMY_FILE, TaxonomyError, load_taxonomy

TAX = load_taxonomy()

# The types Martins approved for Phase 1 (27 Nov 2026). Removing one must be a deliberate change.
REQUIRED = {
    "investment",
    "romance",
    "impersonation_government",
    "impersonation_bank",
    "impersonation_business",
    "purchase_non_delivery",
    "job",
    "tech_support",
    "invoice_redirection_bec",
    "other_scam",
    "unauthorised_fraud",
    "not_a_scam",
}


def test_the_real_file_loads_with_every_required_type() -> None:
    assert set(TAX.ids) == REQUIRED
    assert TAX.version == 1


def test_every_type_maps_to_ftc_and_ic3() -> None:
    for t in TAX.types:
        assert t.ftc, f"{t.id} has no FTC mapping"
        assert t.ic3, f"{t.id} has no IC3 mapping"


def test_unauthorised_fraud_is_the_contrast_case_not_a_scam() -> None:
    assert TAX.get("unauthorised_fraud").authorised_payment is False
    assert TAX.get("not_a_scam").authorised_payment is False
    scams = [t for t in TAX.types if t.id not in {"unauthorised_fraud", "not_a_scam"}]
    assert all(t.authorised_payment for t in scams)


def test_business_email_compromise_feeds_the_simulator() -> None:
    bec = TAX.get("invoice_redirection_bec")
    assert bec.in_simulator
    assert any(m.category == "BEC" and m.match == "exact" for m in bec.ic3)


def test_partial_matches_explain_themselves() -> None:
    """Where no report has a clean match, a note must say how its share is found instead."""
    for t in TAX.types:
        exact = any(m.match == "exact" for m in (*t.ftc, *t.ic3))
        if not exact:
            assert t.note, f"{t.id} has only partial or no matches but no note"


def test_tie_breaks_put_unauthorised_first() -> None:
    assert "unauthorised_fraud" in TAX.tie_breaks[0]


def test_unknown_type_lookup_names_the_choices() -> None:
    with pytest.raises(KeyError, match="known: investment"):
        TAX.get("crypto")


def test_mappings_record_subcategories() -> None:
    romance = TAX.get("romance").ftc[0]
    assert (romance.category, romance.subcategory, romance.match) == (
        "Imposter Scams",
        "Romance Scams",
        "exact",
    )


# --- The loader refuses broken files ---------------------------------------------------------


def _write_variant(tmp_path: Path, change: object) -> Path:
    data = yaml.safe_load(TAXONOMY_FILE.read_text(encoding="utf-8"))
    change(data)  # type: ignore[operator]
    path = tmp_path / "taxonomy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _set(key: str, value: object, index: int = 0) -> object:
    def change(data: dict) -> None:  # type: ignore[type-arg]
        data["types"][index][key] = value

    return change


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["types"].append(dict(d["types"][0])), "duplicate scam type ids: investment"),
        (_set("id", "Investment Scam"), "lower_snake_case"),
        (_set("definition", "  "), "definition is empty"),
        (_set("ftc", []), "needs at least one FTC mapping"),
        (_set("ic3", [{"crime_type": "Investment", "match": "close"}]), "match must be one of"),
        (_set("ic3", [{"crime_type": "none", "match": "exact"}]), "exactly when match is 'none'"),
        (_set("ftc", [{"match": "exact"}]), "FTC mapping has no category"),
        (_set("ftc", ["Investment Related"]), "each FTC mapping must be a mapping"),
        (_set("authorised_payment", "yes"), "'authorised_payment' must be bool"),
        (lambda d: d.pop("tie_breaks"), "missing 'tie_breaks'"),
        (lambda d: d.update(tie_breaks=[]), "tie_breaks must be a non-empty list"),
        (lambda d: d.update(version=True), "'version' must be int"),
        (lambda d: d["types"].__setitem__(0, "investment"), "type #1 must be a mapping"),
        (
            lambda d: [t.update(authorised_payment=True) for t in d["types"]],
            "unauthorised (non-scam) contrast case",
        ),
    ],
)
def test_broken_files_are_refused(tmp_path: Path, change: object, message: str) -> None:
    with pytest.raises(TaxonomyError, match=message.replace("(", r"\(").replace(")", r"\)")):
        load_taxonomy(_write_variant(tmp_path, change))


def test_a_file_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="must be a YAML mapping"):
        load_taxonomy(path)

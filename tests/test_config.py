"""Engine-level messaging configuration: FHIR vs ADT vs both."""

import json

import pytest

from nemsis2fhir.config import MessagingConfig, dispatch
from nemsis2fhir.convert import convert

from .conftest import CHEST_PAIN


@pytest.fixture(scope="module")
def chest_pain():
    return convert(CHEST_PAIN, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]


def test_default_mode_is_fhir(chest_pain):
    report = dispatch(chest_pain)
    assert [e["kind"] for e in report] == ["fhir-transaction"]
    assert report[0]["sent"] is False  # no endpoint configured
    assert report[0]["artifact"]["resourceType"] == "Bundle"


def test_adt_mode_produces_only_messages(chest_pain):
    config = MessagingConfig(mode="adt")
    report = dispatch(chest_pain, config)
    assert [e["kind"] for e in report] == ["adt-a03"]  # completed-call default
    assert report[0]["artifact"].startswith("MSH|")


def test_both_mode_with_prearrival_and_iti65(chest_pain):
    config = MessagingConfig.from_dict({
        "mode": "both",
        "fhir": {"iti65": True},
        "adt": {"send_prearrival": True},
    })
    report = dispatch(chest_pain, config)
    assert [e["kind"] for e in report] == ["fhir-transaction", "iti65", "adt-a04", "adt-a03"]
    assert all(e["sent"] is False for e in report)  # produce-only without endpoints


def test_from_file_and_mode_validation(tmp_path):
    path = tmp_path / "messaging.json"
    path.write_text(json.dumps({"mode": "adt", "adt": {"receiving_facility": "STATE-HIE"}}))
    config = MessagingConfig.from_file(path)
    assert config.wants_adt and not config.wants_fhir
    assert config.adt.receiving_facility == "STATE-HIE"
    with pytest.raises(ValueError):
        MessagingConfig(mode="fax")


def test_ccda_rail(chest_pain, tmp_path):
    pytest.importorskip("nemsis2ccda")
    config = MessagingConfig.from_dict(
        {"mode": ["ccda"], "ccda": {"out_dir": str(tmp_path)}})
    report = dispatch(chest_pain, config)
    assert [e["kind"] for e in report] == ["ccda"]
    assert report[0]["artifact"].lstrip().startswith("<?xml")
    assert "ClinicalDocument" in report[0]["artifact"]
    assert report[0]["sent"] is True
    assert (tmp_path / "PCR-2026-000123.ccda.xml").exists()


def test_rail_list_and_legacy_modes(chest_pain):
    pytest.importorskip("nemsis2ccda")
    report = dispatch(chest_pain, MessagingConfig(mode=["fhir", "adt", "ccda"]))
    assert [e["kind"] for e in report] == ["fhir-transaction", "ccda", "adt-a03"]
    legacy = dispatch(chest_pain, MessagingConfig(mode="both"))
    assert [e["kind"] for e in legacy] == ["fhir-transaction", "adt-a03"]

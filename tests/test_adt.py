"""ADT^A03 projection: the EMS encounter as the ADT visit."""

import pytest

from nemsis2fhir.assemble.adt import build_adt_a03
from nemsis2fhir.convert import convert

from .conftest import CHEST_PAIN, FIXTURES

REFUSAL = FIXTURES / "pcr_refusal.xml"


def _message(path=CHEST_PAIN, **kwargs):
    result = convert(path, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    raw = build_adt_a03(result.context, **kwargs)
    return {seg.split("|", 1)[0]: seg.split("|") for seg in raw.strip("\r").split("\r")}, raw


def test_message_envelope():
    segments, raw = _message(receiving_application="ENS", receiving_facility="STATE-HIE")
    msh = segments["MSH"]
    assert msh[1] == "^~\\&"
    assert msh[2] == "nemsis2fhir"
    assert msh[3] == "Wasatch Valley EMS (synthetic)"
    assert msh[4] == "ENS" and msh[5] == "STATE-HIE"
    assert msh[8] == "ADT^A03^ADT_A03"
    assert msh[10] == "P" and msh[11] == "2.5.1"
    assert segments["EVN"][1] == "A03"
    assert segments["EVN"][2] == "20260806094805-0600"  # transfer of care
    assert raw.endswith("\r")


def test_pid_demographics():
    segments, _ = _message()
    pid = segments["PID"]
    assert "AG-778812^^^4901^PI" in pid[3]
    assert pid[5] == "Trujillo^Elena"
    assert pid[7] == "19800214"
    assert pid[8] == "F"
    assert "1420 Cottonwood Ln" in pid[11]


def test_pv1_visit_and_transported_disposition():
    segments, _ = _message()
    pv1 = segments["PV1"]
    assert pv1[2] == "E"
    assert pv1[3] == "Medic 42"  # the unit is the visit location
    assert "PCR-2026-000123^^^4901^VN" in pv1[19]
    assert pv1[36] == "02"  # transported -> transferred to hospital (NUBC)
    assert pv1[44] == "20260806090610-0600"  # arrived at patient
    assert pv1[45] == "20260806094805-0600"  # transfer of care


def test_refusal_maps_to_ama():
    segments, _ = _message(REFUSAL)
    assert segments["PV1"][36] == "07"  # left AMA / discontinued care
    # refusal has no destination arrival: end-of-visit falls back to left-scene
    assert segments["PV1"][45] == "20260806144100-0600"


def test_dg1_impressions_pass_through():
    _, raw = _message()
    dg1 = [seg for seg in raw.split("\r") if seg.startswith("DG1")]
    assert dg1[0].split("|")[3] == "I21.9^^I10"
    assert dg1[0].split("|")[6] == "F"  # primary = final
    assert dg1[1].split("|")[3] == "I20.9^^I10"
    assert dg1[1].split("|")[6] == "W"  # secondary = working


def test_escaping_and_determinism():
    result = convert(CHEST_PAIN, agency_names={"4901": "Wasatch & Valley | EMS"})[0]
    raw = build_adt_a03(result.context)
    assert "Wasatch \\T\\ Valley \\F\\ EMS" in raw
    assert raw == build_adt_a03(result.context)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.xml")), ids=lambda p: p.stem)
def test_corpus_renders(path):
    segments, raw = _message(path)
    assert set(segments) >= {"MSH", "EVN", "PID", "PV1"}
    assert segments["PV1"][36] in {"01", "02", "07", "20"}

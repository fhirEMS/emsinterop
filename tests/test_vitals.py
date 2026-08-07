"""VitalGroup -> N Observations sharing eVitals.01; NV/PN on measurements."""

from emsinterop.terminology import systems

from .conftest import by_type

GROUP1_TIME = "2026-08-06T09:07:00-06:00"
GROUP2_TIME = "2026-08-06T09:20:00-06:00"


def _vitals(resources):
    return [
        o
        for o in by_type(resources, "Observation")
        if any(
            c.get("code") == "vital-signs"
            for cat in o.get("category", [])
            for c in cat.get("coding", [])
        )
    ]


def _with_loinc(observations, code):
    return [
        o
        for o in observations
        if any(c.get("code") == code and c.get("system") == systems.LOINC
               for c in o["code"]["coding"])
    ]


def test_group_timestamp_shared(resources):
    group1 = [o for o in _vitals(resources) if o.get("effectiveDateTime") == GROUP1_TIME]
    group2 = [o for o in _vitals(resources) if o.get("effectiveDateTime") == GROUP2_TIME]
    assert len(group1) >= 8  # BP, HR, SpO2, RR, glucose, GCS, temp, AVPU, pain, rhythm
    assert len(group2) >= 5
    assert len(group1) + len(group2) == len(_vitals(resources))


def test_blood_pressure_panel(resources):
    bps = _with_loinc(_vitals(resources), "85354-9")
    assert len(bps) == 2
    measured = [b for b in bps if b["effectiveDateTime"] == GROUP1_TIME][0]
    values = {
        c["code"]["coding"][0]["code"]: c.get("valueQuantity", {}).get("value")
        for c in measured["component"]
    }
    assert values == {"8480-6": 142, "8462-4": 88}


def test_nv_blood_pressure_keeps_reason_not_value(resources):
    bps = _with_loinc(_vitals(resources), "85354-9")
    nv_bp = [b for b in bps if b["effectiveDateTime"] == GROUP2_TIME][0]
    for component in nv_bp["component"]:
        assert "valueQuantity" not in component
        dar = component["dataAbsentReason"]["coding"]
        assert any(c["system"] == systems.DATA_ABSENT_REASON and c["code"] == "unknown" for c in dar)
        assert any(c["system"] == systems.NEMSIS and c["code"] == "7701003" for c in dar)


def test_pn_refused_spo2(resources):
    spo2s = _with_loinc(_vitals(resources), "2708-6")
    refused = [o for o in spo2s if o["effectiveDateTime"] == GROUP2_TIME][0]
    assert "valueQuantity" not in refused
    dar = refused["dataAbsentReason"]["coding"]
    assert any(c["code"] == "asked-declined" for c in dar)
    assert any(c["system"] == systems.NEMSIS and c["code"] == "8801019" for c in dar)
    measured = [o for o in spo2s if o["effectiveDateTime"] == GROUP1_TIME][0]
    assert measured["valueQuantity"]["value"] == 91


def test_gcs_total_and_components(resources):
    gcs = _with_loinc(_vitals(resources), "9269-2")
    scored = [g for g in gcs if g["effectiveDateTime"] == GROUP1_TIME][0]
    assert scored["valueQuantity"]["value"] == 15
    component_codes = {c["code"]["coding"][0]["code"] for c in scored["component"]}
    assert component_codes == {"9267-6", "9270-0", "9268-4"}


def test_avpu_dual_coded(resources):
    avpu = [
        o
        for o in _vitals(resources)
        if any(c.get("code") == "eVitals.26" for c in o["code"]["coding"])
    ]
    assert avpu
    coding = avpu[0]["valueCodeableConcept"]["coding"]
    assert any(c["system"] == systems.NEMSIS and c["code"] == "3326001" for c in coding)

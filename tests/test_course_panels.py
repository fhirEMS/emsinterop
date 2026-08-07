"""New panel mappers: eArrest gate, EMS-course observations, prearrival
Communication, vehicle Location, profile claims."""

from nemsis2fhir.terminology import systems

from .conftest import by_type


def _obs_by_nemsis_code(resources, element_id):
    return [
        o
        for o in by_type(resources, "Observation")
        if any(c.get("code") == element_id and c.get("system") == systems.NEMSIS
               for c in o["code"]["coding"])
    ]


def test_arrest_gate_no_is_negative_finding(resources):
    arrest = _obs_by_nemsis_code(resources, "eArrest.01")
    assert len(arrest) == 1
    codes = [c["code"] for c in arrest[0]["valueCodeableConcept"]["coding"]]
    assert "3001001" in codes  # No
    interp = arrest[0]["interpretation"][0]["coding"][0]["code"]
    assert interp == "NEG"


def test_prearrival_alert_no_is_not_done(resources):
    communications = by_type(resources, "Communication")
    assert len(communications) == 1
    alert = communications[0]
    assert alert["status"] == "not-done"
    reason_codes = [c["code"] for c in alert["statusReason"]["coding"]]
    assert "4224001" in reason_codes


def test_vehicle_location(resources):
    vehicles = [
        l for l in by_type(resources, "Location")
        if l.get("physicalType", {}).get("coding", [{}])[0].get("code") == "ve"
    ]
    assert len(vehicles) == 1
    assert vehicles[0]["name"] == "Medic 42"
    assert vehicles[0]["identifier"][0]["value"] == "M42"
    encounter = by_type(resources, "Encounter")[0]
    location_refs = {loc["location"]["reference"] for loc in encounter["location"]}
    assert f"Location/{vehicles[0]['id']}" in location_refs


def test_course_observations(resources):
    emd = _obs_by_nemsis_code(resources, "eDispatch.02")
    assert emd and emd[0]["valueCodeableConcept"]["coding"][0]["code"] == "2302003"
    protocol = _obs_by_nemsis_code(resources, "eProtocols.01")
    assert protocol
    codes = [c["code"] for c in protocol[0]["valueCodeableConcept"]["coding"]]
    assert "9914117" in codes  # Medical-Cardiac Chest Pain
    component = protocol[0]["component"][0]["valueCodeableConcept"]["coding"]
    assert any(c["code"] == "3602001" for c in component)  # Adult Only
    crew_disp = _obs_by_nemsis_code(resources, "eDisposition.29")
    assert crew_disp and any(
        c["code"] == "4229001" for c in crew_disp[0]["valueCodeableConcept"]["coding"]
    )


def test_stroke_scale_nv_preserved(resources):
    stroke = _obs_by_nemsis_code(resources, "eVitals.29")
    assert len(stroke) == 2  # one per VitalGroup, both NV
    for obs in stroke:
        dar = obs["dataAbsentReason"]["coding"]
        assert any(c["system"] == systems.NEMSIS and c["code"] == "7701003" for c in dar)


def test_us_core_profile_claims(resources):
    def profiles(resource):
        return resource.get("meta", {}).get("profile", [])

    patient = by_type(resources, "Patient")[0]
    assert any(p.endswith("us-core-patient") for p in profiles(patient))
    encounter = by_type(resources, "Encounter")[0]
    assert any(p.endswith("us-core-encounter") for p in profiles(encounter))
    bp = [
        o for o in by_type(resources, "Observation")
        if any(c.get("code") == "85354-9" for c in o["code"]["coding"])
    ]
    assert bp and any(p.endswith("us-core-blood-pressure") for p in profiles(bp[0]))
    spo2 = [
        o for o in by_type(resources, "Observation")
        if any(c.get("code") == "59408-5" for c in o["code"]["coding"])
    ]
    assert spo2, "pulse-ox must carry the US Core primary code 59408-5"
    assert any(p.endswith("us-core-pulse-oximetry") for p in profiles(spo2[0]))


def test_organization_name_absent_reason_placement(resources):
    org = by_type(resources, "Organization")[0]
    assert "extension" not in org  # old resource-level placement removed
    dar = org["_name"]["extension"][0]
    assert dar["url"] == systems.DATA_ABSENT_REASON_EXT

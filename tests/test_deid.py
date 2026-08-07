"""Safe Harbor de-id projection: allowlist-by-construction analytics tables
over a fhirEngine-shaped Delta store. Skipped without the analytics extra."""

import json

import pytest

deltalake = pytest.importorskip("deltalake")
duckdb = pytest.importorskip("duckdb")

from emsinterop.analytics.deid import (  # noqa: E402
    capped_age,
    project,
    year_of,
    zip3,
)
from emsinterop.convert import convert  # noqa: E402

from .conftest import CHEST_PAIN  # noqa: E402


def test_safe_harbor_primitives():
    assert zip3("84101") == "841"
    assert zip3("03601") is None  # restricted low-population prefix
    assert zip3(None) is None and zip3("8") is None
    assert year_of("2026-08-06T09:04:45-06:00") == 2026
    assert capped_age("1935-01-15", "2026-08-06") == 90  # 91 caps to 90
    assert capped_age("1980-06-01", "2026-08-06") == 46
    assert capped_age(None, "2026-08-06") is None


def _write_tier(base, resource_type, bodies, versions=None):
    import pyarrow as pa
    from deltalake import write_deltalake

    rows = {
        "id": [b["id"] for b in bodies],
        "version_id": versions or [1] * len(bodies),
        "deleted": [False] * len(bodies),
        "body_json": [json.dumps(b) for b in bodies],
    }
    write_deltalake(str(base / "bronze" / resource_type), pa.table(rows),
                    mode="append")


@pytest.fixture()
def fhirengine_base(tmp_path):
    """A fhirEngine-shaped single-mode Delta store fed from the corpus, plus a
    synthetic 90+ patient in a restricted ZIP to exercise the caps."""
    result = convert(CHEST_PAIN)[0]
    patients = [r for r in result.resources if r["resourceType"] == "Patient"]
    encounters = [r for r in result.resources if r["resourceType"] == "Encounter"]
    observations = [r for r in result.resources if r["resourceType"] == "Observation"]

    elderly = {
        "resourceType": "Patient", "id": "elder-1",
        "name": [{"family": "Winterbourne", "given": ["Agatha"]}],
        "birthDate": "1931-02-03",
        "address": [{"postalCode": "03601", "state": "33",
                     "line": ["9 Hermit Hollow"]}],
        "gender": "female",
    }
    elder_encounter = {
        "resourceType": "Encounter", "id": "elder-enc-1", "status": "finished",
        "subject": {"reference": "Patient/elder-1"},
        "period": {"start": "2026-05-01T10:00:00Z"},
    }
    # Two versions of the elderly patient: only v2's address may project.
    base = tmp_path / "delta"
    _write_tier(base, "patient", patients)
    _write_tier(base, "patient",
                [{**elderly, "address": [{"postalCode": "84101", "state": "49"}]},
                 elderly],
                versions=[1, 2])
    _write_tier(base, "encounter", encounters + [elder_encounter])
    _write_tier(base, "observation", observations)
    return base, result


def test_projection_is_deidentified(fhirengine_base, tmp_path):
    base, result = fhirengine_base
    out = tmp_path / "deid"
    summary = project(base, out)
    assert summary["encounters"] == 2
    assert summary["vitals"] > 0

    encounters = deltalake.DeltaTable(str(out / "encounters")).to_pyarrow_table()
    vitals = deltalake.DeltaTable(str(out / "vitals")).to_pyarrow_table()

    # No identifying string from either patient anywhere in the output.
    serialized = json.dumps(encounters.to_pylist()) + json.dumps(vitals.to_pylist())
    for phi in ("Trujillo", "Elena", "Cottonwood", "801-555-0142", "Winterbourne",
                "Hermit Hollow", "84101", "03601", "1931", "elder-1"):
        assert phi not in serialized, f"identifier leaked: {phi}"
    # Nor any raw resource id (pseudonyms only).
    for resource in result.resources:
        assert resource["id"] not in serialized

    rows = {r["patient_pseudo_id"]: r for r in encounters.to_pylist()}
    assert len(rows) == 2
    elder = next(r for r in encounters.to_pylist() if r["age"] == 90)
    assert elder["zip3"] is None  # restricted prefix nulled (current version wins)
    assert elder["year"] == 2026

    corpus = next(r for r in encounters.to_pylist() if r["age"] != 90)
    assert corpus["zip3"] == "841"
    assert corpus["gender"] == "female"
    assert corpus["race_omb"] == "2106-3" and corpus["ethnicity_omb"] == "2135-2"
    assert corpus["priority_nemsis"] == "2223001"


def test_projection_links_vitals_to_encounter(fhirengine_base, tmp_path):
    base, result = fhirengine_base
    out = tmp_path / "deid"
    project(base, out, salt="stable-test-salt")
    encounters = deltalake.DeltaTable(str(out / "encounters")).to_pyarrow_table().to_pylist()
    vitals = deltalake.DeltaTable(str(out / "vitals")).to_pyarrow_table().to_pylist()

    encounter_ids = {r["encounter_pseudo_id"] for r in encounters}
    assert vitals and all(v["encounter_pseudo_id"] in encounter_ids for v in vitals)
    assert all(isinstance(v["value"], float) for v in vitals)

    # Stable salt → stable pseudonyms across runs (cross-run linkage).
    project(base, tmp_path / "deid2", salt="stable-test-salt")
    again = deltalake.DeltaTable(str(tmp_path / "deid2" / "encounters")).to_pyarrow_table().to_pylist()
    assert {r["encounter_pseudo_id"] for r in again} == encounter_ids

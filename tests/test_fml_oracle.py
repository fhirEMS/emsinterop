"""CI fidelity oracle (ADR-002): the reference Java FML engine executes the
authored StructureMaps and its output must match the native Python mapper on
the map-covered surface.

Java lives ONLY here (CI), never in the runtime. Skipped unless
EMSINTEROP_FML_ORACLE=1 with java + validator_cli.jar available. The
validator's transform mode requires a terminology server; a local fhirEngine
(EMSINTEROP_TIER1_URL or EMSINTEROP_ORACLE_TX) makes the oracle fully
network-free — verified to produce output identical to tx.fhir.org. Falls back
to tx.fhir.org when no local server is configured.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from emsinterop.ingest import parse
from emsinterop.mapping import map_pcr
from emsinterop.oracle import (
    bp_oracle_projection,
    condition_oracle_projection,
    emedication_group_instances,
    epatient_instance,
    eprocedure_group_instances,
    esituation_instance,
    evitals_group_instances,
    medadmin_oracle_projection,
    patient_oracle_projection,
    procedure_oracle_projection,
)

from emsinterop import conformance

from .conftest import FIXTURES

REPO = Path(__file__).resolve().parents[1]
JAR = Path(os.environ.get("EMSINTEROP_VALIDATOR_JAR", Path.home() / "Downloads" / "validator_cli.jar"))
# Prefer a local fhirEngine as the tx server (network-free oracle); fall back
# to tx.fhir.org. fhirEngine doesn't pass the validator's tx approval battery
# yet, so the authorise flag is always passed (harmless for tx.fhir.org).
TX = (
    os.environ.get("EMSINTEROP_ORACLE_TX")
    or os.environ.get("EMSINTEROP_TIER1_URL")
    or "http://tx.fhir.org"
)
ENABLED = os.environ.get("EMSINTEROP_FML_ORACLE") == "1" and shutil.which("java") and JAR.exists()

pytestmark = pytest.mark.skipif(
    not ENABLED,
    reason="set EMSINTEROP_FML_ORACLE=1 (java + validator_cli.jar + network tx) to run the FML oracle",
)

ALL_FIXTURES = sorted(FIXTURES.glob("*.xml"))


def _reference_transform(map_url: str, instance: dict, tmp_path: Path) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "instance.json"
    source.write_text(json.dumps(instance))
    output = tmp_path / "reference.json"
    run = subprocess.run(
        [
            "java", "-jar", str(JAR), "transform", map_url, str(source),
            "-version", "4.0.1",
            "-ig", str(REPO / "maps" / "logical"),
            "-ig", str(REPO / "maps" / "conceptmaps"),
            "-ig", str(REPO / "maps" / "structuremaps"),
            "-tx", TX,
            "-authorise-non-conformant-tx-servers",
            "-output", str(output),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert output.exists(), f"transform produced no output:\n{run.stdout[-2000:]}\n{run.stderr[-2000:]}"
    return json.loads(output.read_text())


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_patient_map_matches_native_mapper(path, tmp_path):
    dataset = parse(path)
    pcr = dataset.reports[0]

    reference = _reference_transform(
        conformance.canonical("StructureMap", "NemsisEPatientToPatient"),
        epatient_instance(pcr),
        tmp_path,
    )

    ctx = map_pcr(dataset, pcr)
    native = next(r for r in ctx.resources if r["resourceType"] == "Patient")

    assert patient_oracle_projection(reference) == patient_oracle_projection(native)


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_medication_map_matches_native_mapper(path, tmp_path):
    """Per MedicationGroup: the reference engine's MedicationAdministration —
    including the PN -> not-done + statusReason branch — must match the native
    mapper on the map-covered surface."""
    dataset = parse(path)
    pcr = dataset.reports[0]
    instances = emedication_group_instances(pcr)

    ctx = map_pcr(dataset, pcr)
    natives = [r for r in ctx.resources if r["resourceType"] == "MedicationAdministration"]
    assert len(natives) == len(instances)

    for index, (instance, native) in enumerate(zip(instances, natives)):
        reference = _reference_transform(
            conformance.canonical("StructureMap", "NemsisEMedicationsToMedicationAdministration"),
            instance,
            tmp_path / str(index),
        )
        assert medadmin_oracle_projection(reference) == medadmin_oracle_projection(native), (
            f"group {index} diverged"
        )


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_bp_map_matches_native_mapper(path, tmp_path):
    """Per VitalGroup: the BP panel Observation — shared group timestamp,
    components with value XOR dual-coded data-absent-reason — must match
    between the reference engine and the native mapper."""
    dataset = parse(path)
    pcr = dataset.reports[0]
    instances = evitals_group_instances(pcr)

    ctx = map_pcr(dataset, pcr)
    natives = [
        r for r in ctx.resources
        if r["resourceType"] == "Observation"
        and any(c.get("code") == "85354-9" for c in r.get("code", {}).get("coding", []))
    ]
    # A BP Observation exists per group whose source had SBP or DBP (value or nil).
    comparable = [i for i in instances if "eVitals_06" in i or "eVitals_06_nv" in i
                  or "eVitals_07" in i or "eVitals_07_nv" in i]
    assert len(natives) == len(comparable)

    for index, (instance, native) in enumerate(zip(comparable, natives)):
        reference = _reference_transform(
            conformance.canonical("StructureMap", "NemsisEVitalsToBPObservation"),
            instance,
            tmp_path / str(index),
        )
        assert bp_oracle_projection(reference) == bp_oracle_projection(native), (
            f"vital group {index} diverged"
        )


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_procedure_map_matches_native_mapper(path, tmp_path):
    """Per ProcedureGroup: SNOMED pass-through / PN -> not-done + statusReason."""
    dataset = parse(path)
    pcr = dataset.reports[0]
    instances = eprocedure_group_instances(pcr)

    ctx = map_pcr(dataset, pcr)
    natives = [r for r in ctx.resources if r["resourceType"] == "Procedure"]
    assert len(natives) == len(instances)

    for index, (instance, native) in enumerate(zip(instances, natives)):
        reference = _reference_transform(
            conformance.canonical("StructureMap", "NemsisEProceduresToProcedure"),
            instance,
            tmp_path / str(index),
        )
        assert procedure_oracle_projection(reference) == procedure_oracle_projection(native), (
            f"procedure group {index} diverged"
        )


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_situation_map_matches_native_mapper(path, tmp_path):
    """Primary impression: ICD-10-CM pass-through Condition with onset."""
    dataset = parse(path)
    pcr = dataset.reports[0]
    instance = esituation_instance(pcr)
    assert instance is not None, "corpus fixtures all carry a primary impression"

    ctx = map_pcr(dataset, pcr)
    native = next(
        r for r in ctx.resources
        if r["resourceType"] == "Condition"
        and any(cat.get("coding", [{}])[0].get("code") == "encounter-diagnosis"
                for cat in r.get("category", []))
    )

    reference = _reference_transform(
        conformance.canonical("StructureMap", "NemsisESituationToCondition"),
        instance,
        tmp_path,
    )
    assert condition_oracle_projection(reference) == condition_oracle_projection(native)

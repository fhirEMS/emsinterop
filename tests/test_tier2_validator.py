"""Tier-2: the official HL7 validator — the AUTHORITATIVE conformance verdict
(Architecture §5.5b; fhirEngine Tier-1 is the submission gate, not full L5).

Skipped unless java + validator_cli.jar are available and EMSINTEROP_TIER2=1
(each document takes ~10-15s to validate). mPSC/IPS profile checks are
deferred until a pinnable (non-draft) mPSC package exists.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from emsinterop.convert import convert

from .conftest import FIXTURES

JAR = Path(os.environ.get("EMSINTEROP_VALIDATOR_JAR", Path.home() / "Downloads" / "validator_cli.jar"))
ENABLED = os.environ.get("EMSINTEROP_TIER2") == "1" and shutil.which("java") and JAR.exists()
SD_DIR = Path(__file__).resolve().parents[1] / "maps" / "structuredefinitions"

pytestmark = pytest.mark.skipif(
    not ENABLED,
    reason="set EMSINTEROP_TIER2=1 (java + validator_cli.jar required) to run Tier-2",
)

# The hostile corpus rides Tier-2 too: the official validator is the
# authoritative verdict on vs-1 and US Core min-cardinality, which is exactly
# what those fixtures exist to pin.
ALL_FIXTURES = sorted(FIXTURES.glob("*.xml")) + sorted(
    (FIXTURES / "hostile").glob("*.xml")
)


#: Fixtures that CANNOT be US Core conformant, with the reason. Not a way to
#: silence inconvenient failures — each entry is a limitation of the standard
#: meeting a fact of the source data, and it is documented in the README.
KNOWN_NON_CONFORMANT = {
    "hostile_sex_refused":
        "the patient refused to state their sex, so Patient cannot claim "
        "us-core-patient (gender is min=1) — and US Core requires every "
        "subject reference to point at a us-core-patient, so the "
        "non-conformance cascades to Encounter/Condition/Observation. "
        "Conforming would mean inventing a gender the source never recorded.",
}


def _validate(payload: dict, path, extra_igs: list[str]) -> None:
    path.write_text(json.dumps(payload))
    run = subprocess.run(
        [
            "java", "-jar", str(JAR), str(path),
            "-version", "4.0.1",
            "-ig", "hl7.fhir.us.core#6.1.0",
            "-ig", str(SD_DIR),
            *[arg for ig in extra_igs for arg in ("-ig", ig)],
            "-tx", "n/a",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = run.stdout + run.stderr
    errors = [l for l in output.splitlines() if "Error @" in l]
    assert "Success: 0 errors" in output, "\n".join(errors[:15]) or output[-2000:]


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_document_passes_hl7_validator(path, tmp_path):
    if path.stem in KNOWN_NON_CONFORMANT:
        pytest.xfail(KNOWN_NON_CONFORMANT[path.stem])
    result = convert(path, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    _validate(result.document, tmp_path / f"{path.stem}_document.json", [])


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_iti65_passes_mhd_validation(path, tmp_path):
    if path.stem in KNOWN_NON_CONFORMANT:
        pytest.xfail(KNOWN_NON_CONFORMANT[path.stem])
    """The ITI-65 Provide Document Bundle conforms to MHD 4.2.2 Minimal
    Metadata (closed ProvideBundle slicing, EntryUUID identifiers)."""
    from emsinterop.transport import provide_document_bundle

    result = convert(path, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    _validate(
        provide_document_bundle(result),
        tmp_path / f"{path.stem}_iti65.json",
        ["ihe.iti.mhd#4.2.2"],
    )

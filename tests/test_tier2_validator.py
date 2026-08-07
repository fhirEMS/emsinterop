"""Tier-2: the official HL7 validator — the AUTHORITATIVE conformance verdict
(Architecture §5.5b; fhirEngine Tier-1 is the submission gate, not full L5).

Skipped unless java + validator_cli.jar are available and NEMSIS2FHIR_TIER2=1
(each document takes ~10-15s to validate). mPSC/IPS profile checks are
deferred until a pinnable (non-draft) mPSC package exists.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from nemsis2fhir.convert import convert

from .conftest import FIXTURES

JAR = Path(os.environ.get("NEMSIS2FHIR_VALIDATOR_JAR", Path.home() / "Downloads" / "validator_cli.jar"))
ENABLED = os.environ.get("NEMSIS2FHIR_TIER2") == "1" and shutil.which("java") and JAR.exists()
SD_DIR = Path(__file__).resolve().parents[1] / "maps" / "structuredefinitions"

pytestmark = pytest.mark.skipif(
    not ENABLED,
    reason="set NEMSIS2FHIR_TIER2=1 (java + validator_cli.jar required) to run Tier-2",
)

ALL_FIXTURES = sorted(FIXTURES.glob("*.xml"))


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
    result = convert(path, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    _validate(result.document, tmp_path / f"{path.stem}_document.json", [])


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_iti65_passes_mhd_validation(path, tmp_path):
    """The ITI-65 Provide Document Bundle conforms to MHD 4.2.2 Minimal
    Metadata (closed ProvideBundle slicing, EntryUUID identifiers)."""
    from nemsis2fhir.transport import provide_document_bundle

    result = convert(path, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    _validate(
        provide_document_bundle(result),
        tmp_path / f"{path.stem}_iti65.json",
        ["ihe.iti.mhd#4.2.2"],
    )

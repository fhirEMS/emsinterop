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


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
def test_document_passes_hl7_validator(path, tmp_path):
    result = convert(path, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    doc = tmp_path / f"{path.stem}_document.json"
    doc.write_text(json.dumps(result.document))
    run = subprocess.run(
        [
            "java", "-jar", str(JAR), str(doc),
            "-version", "4.0.1",
            "-ig", "hl7.fhir.us.core#6.1.0",
            "-ig", str(SD_DIR),
            "-tx", "n/a",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = run.stdout + run.stderr
    errors = [l for l in output.splitlines() if "Error @" in l]
    assert "Success: 0 errors" in output, "\n".join(errors[:15]) or output[-2000:]

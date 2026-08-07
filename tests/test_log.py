"""PHI-safe logging: the structural allowlist and the corpus-wide guarantee
that a full pipeline run at DEBUG never emits a patient value."""

import logging

import pytest
from lxml import etree

from emsinterop.convert import convert
from emsinterop.log import ALLOWED_FIELDS, event, get_logger

from .conftest import FIXTURES

NEMSIS_NS = "http://www.nemsis.org"


def test_event_emits_only_allowlisted_fields(caplog):
    logger = get_logger("test")
    with caplog.at_level(logging.DEBUG, logger="emsinterop"):
        event(logger, "unit.test", pcr_number="PCR-9", patient_name="Elena",
              resources=4)
    assert len(caplog.records) == 1
    line = caplog.text
    assert "pcr_number=PCR-9" in line and "resources=4" in line
    assert "Elena" not in line  # the VALUE never appears...
    assert "dropped_fields=patient_name" in line  # ...only the field name


def test_event_respects_logger_level(caplog):
    logger = get_logger("test")
    with caplog.at_level(logging.WARNING, logger="emsinterop"):
        event(logger, "unit.quiet", pcr_number="PCR-9")
    assert caplog.records == []


def test_allowlist_carries_no_value_shaped_fields():
    # Nothing in the allowlist may name patient content.
    for banned in ("name", "birth", "address", "phone", "narrative", "value",
                   "text", "ssn"):
        assert not any(banned in field for field in ALLOWED_FIELDS), banned


def _patient_values(xml_path):
    """The directly identifying strings in a fixture: name, street, DOB."""
    root = etree.parse(str(xml_path)).getroot()
    values = set()
    for element in ("ePatient.02", "ePatient.03", "ePatient.05", "ePatient.17"):
        for node in root.iter(f"{{{NEMSIS_NS}}}{element}"):
            if node.text and node.text.strip():
                values.add(node.text.strip())
    return values


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("pcr_*.xml")),
                         ids=lambda p: p.stem)
def test_pipeline_logs_carry_no_phi(fixture, caplog):
    phi = _patient_values(fixture)
    assert phi, f"{fixture.name} has no patient values to test against"
    with caplog.at_level(logging.DEBUG, logger="emsinterop"):
        convert(fixture)
    assert caplog.records, "conversion emitted no log events"
    for value in phi:
        assert value not in caplog.text, f"PHI value leaked into logs: {value!r}"

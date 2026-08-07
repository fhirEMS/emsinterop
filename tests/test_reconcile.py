"""Issue-log persistence + dead-letter reconciliation (Roadmap P5).

The gap-register feed: conversion issues serialize to JSONL, submit-time
atomic rejections fold into the log (fhirEngine never dead-letters a rejected
transaction), and per-resource dead-letter rows join back to their PCR by
deterministic resource id or PCR business identifier."""

import json

import pytest

from emsinterop.issues import (
    ConversionIssue,
    Disposition,
    IssueLog,
    issues_from_operation_outcome,
    read_jsonl,
)

from .conftest import CHEST_PAIN, by_type


def test_issues_from_operation_outcome():
    outcome = {
        "resourceType": "OperationOutcome",
        "issue": [
            {"severity": "error", "code": "code-invalid",
             "expression": ["Observation.code"],
             "diagnostics": "code 4512345 not in ValueSet vitals"},
            {"severity": "fatal", "code": "structure",
             "details": {"text": "bad cardinality"}},
        ],
    }
    issues = issues_from_operation_outcome(outcome, "PCR-1", 422)
    assert len(issues) == 2
    assert issues[0].element_id == "Observation.code"
    assert issues[0].disposition is Disposition.INVALID
    assert "HTTP 422" in issues[0].reason and "code-invalid" in issues[0].reason
    assert issues[1].severity == "error"  # fatal folds to error
    assert issues[1].element_id == "transaction"  # no expression/location
    assert "bad cardinality" in issues[1].reason


def test_issues_from_operation_outcome_no_body():
    issues = issues_from_operation_outcome(None, "PCR-1", 500)
    assert len(issues) == 1
    assert issues[0].element_id == "transaction"
    assert issues[0].severity == "error"


def test_issue_log_jsonl_roundtrip(tmp_path):
    log = IssueLog()
    log.add("PCR-1", "eVitals.14", Disposition.UNMAPPED, "no target", "warning")
    log.add(None, "eOther.09", Disposition.DEFERRED, "phase 6")
    path = tmp_path / "issues.jsonl"
    assert log.write_jsonl(path) == 2
    assert log.write_jsonl(path) == 2  # append mode: a second sweep adds rows

    loaded = read_jsonl(path)
    assert len(loaded) == 4
    assert loaded.issues[:2] == log.issues
    assert loaded.issues[1].disposition is Disposition.DEFERRED


def test_dispatch_captures_submission_error(monkeypatch):
    import emsinterop.submit as submit
    from emsinterop.config import MessagingConfig, dispatch
    from emsinterop.convert import convert

    outcome = {"resourceType": "OperationOutcome",
               "issue": [{"severity": "error", "code": "invariant",
                          "expression": ["Bundle.entry[3]"],
                          "diagnostics": "reference cycle"}]}

    class RejectingClient:
        def __init__(self, *args, **kwargs):
            pass

        def submit(self, bundle):
            raise submit.SubmissionError(422, outcome)

    monkeypatch.setattr(submit, "FhirEngineClient", RejectingClient)
    result = convert(CHEST_PAIN)[0]
    before = len(result.issues)
    config = MessagingConfig.from_dict(
        {"mode": "fhir", "fhir": {"fhirengine_url": "http://x"}})

    report = dispatch(result, config)

    entry = report[0]
    assert entry["sent"] is False
    assert entry["error"] == "HTTP 422"
    assert entry["outcome"] == outcome
    captured = result.issues.issues[before:]
    assert [i.element_id for i in captured] == ["Bundle.entry[3]"]
    assert captured[0].pcr_number == result.context.pcr_number


deltalake = pytest.importorskip("deltalake")


def _write_dead_letter(delta_base, resource_type, rows):
    import pyarrow as pa
    from deltalake import write_deltalake

    table = pa.table({
        "id": [r["id"] for r in rows],
        "resourceType": [resource_type] * len(rows),
        "error": [r.get("error", "validation failed") for r in rows],
        "body_json": [json.dumps(r.get("body", {})) for r in rows],
        "failed_at": ["2026-08-07T12:00:00Z"] * len(rows),
    })
    write_deltalake(str(delta_base / "deadletter" / resource_type.lower()),
                    table, mode="append")


def test_dead_letter_reconciliation(tmp_path):
    from emsinterop.convert import convert
    from emsinterop.ingest.bronze import land
    from emsinterop.reconcile import reconcile_bronze

    bronze = tmp_path / "bronze"
    land(CHEST_PAIN, bronze)
    converted = convert(CHEST_PAIN)[0]
    pcr_number = converted.context.pcr_number
    observation = by_type(converted.resources, "Observation")[0]

    delta_base = tmp_path / "fhirengine-delta"
    # Row 1 joins by deterministic resource id; row 2 has an id we no longer
    # produce but carries the PCR business identifier in its body; row 3 is
    # somebody else's resource entirely.
    _write_dead_letter(delta_base, "Observation", [
        {"id": observation["id"], "error": "code-invalid: 4512345",
         "body": {"resourceType": "Observation"}},
    ])
    _write_dead_letter(delta_base, "Encounter", [
        {"id": "not-a-current-id",
         "body": {"resourceType": "Encounter",
                  "identifier": [{"system": "urn:nemsis:identifier:pcr",
                                  "value": pcr_number}]}},
        {"id": "someone-elses",
         "body": {"resourceType": "Encounter",
                  "identifier": [{"system": "urn:nemsis:identifier:pcr",
                                  "value": "PCR-OTHER-AGENCY"}]}},
    ])

    register = reconcile_bronze(bronze, delta_base)

    mine = next(p for p in register["pcrs"] if p["pcr_number"] == pcr_number)
    assert {row["id"] for row in mine["dead_letter"]} == {
        observation["id"], "not-a-current-id"}
    assert mine["resource_count"] == len(converted.resources)
    assert mine["issues"] == converted.issues.to_dicts()
    assert [r["id"] for r in register["unmatched_dead_letter"]] == ["someone-elses"]


def test_dead_letter_rows_empty_base(tmp_path):
    from emsinterop.reconcile import dead_letter_rows

    assert dead_letter_rows(tmp_path) == []  # no deadletter/ dir at all

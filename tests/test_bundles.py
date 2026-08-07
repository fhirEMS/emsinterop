"""Transaction bundle, idempotent ids, Provenance, document assembly."""

import copy

from nemsis2fhir.convert import convert
from nemsis2fhir.ingest import parse
from nemsis2fhir.mapping import map_pcr
from nemsis2fhir.assemble import build_composition
from nemsis2fhir.submit import transaction_bundle

from .conftest import CHEST_PAIN, by_type


def test_transaction_shape(result):
    bundle = result.transaction
    assert bundle["type"] == "transaction"
    assert bundle["identifier"]["value"] == "PCR-2026-000123"
    for entry in bundle["entry"]:
        resource = entry["resource"]
        assert entry["fullUrl"] == f"urn:uuid:{resource['id']}"
        assert entry["request"]["method"] == "PUT"
        url = entry["request"]["url"]
        # Conditional upsert (fhirEngine has no update-as-create): resources
        # match on the deterministic resource-id identifier; Provenance on its
        # Patient target; Composition on the PCR business identifier.
        if resource["resourceType"] == "Provenance":
            assert url.startswith("Provenance?target=Patient/")
        elif resource["resourceType"] == "Composition":
            assert url.startswith("Composition?identifier=")
        else:
            assert url == (
                f"{resource['resourceType']}?identifier="
                f"urn:nemsis2fhir:resource-id|{resource['id']}"
            )
            assert any(
                i.get("system") == "urn:nemsis2fhir:resource-id"
                and i.get("value") == resource["id"]
                for i in resource["identifier"]
            )


def test_deterministic_idempotent_ids():
    first = convert(CHEST_PAIN)[0]
    second = convert(CHEST_PAIN)[0]
    ids_first = sorted(r["id"] for r in first.resources)
    ids_second = sorted(r["id"] for r in second.resources)
    assert ids_first == ids_second


def test_provenance_targets_everything(result):
    provenance = by_type(result.resources, "Provenance")[0]
    targeted = {t["reference"] for t in provenance["target"]}
    expected = {
        f"{r['resourceType']}/{r['id']}"
        for r in result.resources
        if r["resourceType"] not in ("Provenance", "Composition")
    }
    assert expected <= targeted
    assert "recorded" in provenance  # stamped by the bundle builder
    assert provenance["entity"][0]["what"]["identifier"]["value"] == "PCR-2026-000123"


def test_mapping_version_tag(result):
    for resource in result.resources:
        tags = resource["meta"]["tag"]
        assert any(t["system"] == "urn:nemsis2fhir:mapping-ruleset" for t in tags)


def test_document_bundle_composition_first(result):
    document = result.document
    assert document["type"] == "document"
    assert document["entry"][0]["resource"]["resourceType"] == "Composition"


def test_composition_sections_and_confidentiality(result):
    composition = result.composition
    # eHistory.17 substance use is present -> document must be restricted.
    assert composition["confidentiality"] == "R"
    titles = {s["title"] for s in composition["section"]}
    assert {"Problems", "Allergies and Intolerances", "Medication Summary",
            "Vital Signs", "Procedures"} <= titles
    for section in composition["section"]:
        assert "entry" in section or "emptyReason" in section


def test_empty_mandatory_sections_get_empty_reason():
    dataset = parse(CHEST_PAIN)
    pcr = dataset.reports[0]
    # Strip history + meds: Allergies and Medication Summary must go empty.
    pcr.sections.pop("eHistory")
    pcr.sections.pop("eMedications")
    ctx = map_pcr(dataset, pcr)
    composition = build_composition(ctx)
    sections = {s["title"]: s for s in composition["section"]}
    allergies = sections["Allergies and Intolerances"]
    assert "entry" not in allergies
    assert allergies["emptyReason"]["coding"][0]["code"] == "unavailable"
    meds = sections["Medication Summary"]
    assert "emptyReason" in meds


def test_cs_variant_last_vitals_only():
    dataset = parse(CHEST_PAIN)
    ctx = map_pcr(dataset, dataset.reports[0])
    composition = build_composition(ctx, variant="CS")
    vitals = [s for s in composition["section"] if s["title"] == "Vital Signs"][0]
    refs = {e["reference"] for e in vitals["entry"]}
    observations = {f"Observation/{r['id']}": r for r in ctx.resources
                    if r["resourceType"] == "Observation"}
    for ref in refs:
        assert observations[ref]["effectiveDateTime"] == "2026-08-06T09:20:00-06:00"


def test_bundle_builder_stamps_recorded():
    dataset = parse(CHEST_PAIN)
    ctx = map_pcr(dataset, dataset.reports[0])
    bundle = transaction_bundle(ctx.resources, recorded="2026-08-06T10:00:00+00:00")
    provenance = [e["resource"] for e in bundle["entry"]
                  if e["resource"]["resourceType"] == "Provenance"][0]
    assert provenance["recorded"] == "2026-08-06T10:00:00+00:00"

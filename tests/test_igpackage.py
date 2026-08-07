"""The emsinterop.nemsis FHIR package: NEMSIS registry + authored maps/
artifacts rendered as an unpacked package fhirEngine's install-ig consumes."""

import json

from emsinterop.terminology import registry, systems
from emsinterop.terminology.conceptmaps import maps_dir
from emsinterop.terminology.igpackage import (
    PACKAGE_NAME,
    VALUESET_URL_BASE,
    build_package,
    package_version,
)


def test_build_package_layout_and_manifest(tmp_path):
    summary = build_package(tmp_path)
    manifest = json.loads((tmp_path / "package.json").read_text())
    assert manifest["name"] == PACKAGE_NAME == summary["package"]
    assert manifest["version"] == package_version()
    assert manifest["fhirVersions"] == ["4.0.1"]

    # Every non-manifest file is a parseable FHIR resource — the exact
    # contract of fhirEngine's readPackageResources().
    files = [p for p in tmp_path.iterdir() if p.name != "package.json"]
    assert files
    for path in files:
        assert json.loads(path.read_text())["resourceType"] in {
            "CodeSystem", "ValueSet", "ConceptMap", "StructureDefinition"}


def test_codesystem_covers_registry_deduped(tmp_path):
    build_package(tmp_path)
    cs = json.loads((tmp_path / "CodeSystem-nemsis.json").read_text())
    assert cs["url"] == systems.NEMSIS
    assert cs["content"] == "fragment"  # local clean subset, never "complete"

    codes = [c["code"] for c in cs["concept"]]
    assert len(codes) == len(set(codes)) == cs["count"]
    every_code = {code for element, codes_ in registry.elements().items()
                  for code in codes_ if code != "__name__"}
    assert set(codes) == every_code
    by_code = {c["code"]: c.get("display") for c in cs["concept"]}
    assert by_code["4001001"].startswith("Adequate Airway")
    assert "7701001" in by_code  # NV codes present exactly once


def test_valueset_per_element(tmp_path):
    build_package(tmp_path)
    vs_files = sorted(tmp_path.glob("ValueSet-*.json"))
    assert len(vs_files) == len(registry.elements())

    airway = json.loads((tmp_path / "ValueSet-nemsis-eAirway-01.json").read_text())
    assert airway["url"] == f"{VALUESET_URL_BASE}eAirway.01"
    include = airway["compose"]["include"][0]
    assert include["system"] == systems.NEMSIS
    assert {"code": "4001003", "display": "Airway Reflex Compromised"} in include["concept"]
    assert not any(c["code"] == "__name__" for c in include["concept"])


def test_authored_artifacts_copied_verbatim(tmp_path):
    summary = build_package(tmp_path)
    maps_root = maps_dir().parent
    authored = [p for sub in ("conceptmaps", "structuredefinitions", "logical")
                for p in sorted((maps_root / sub).glob("*.json"))]
    assert summary["authored_artifacts"] == len(authored) > 0
    for source in authored:
        assert (tmp_path / source.name).read_bytes() == source.read_bytes()

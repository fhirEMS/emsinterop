"""FHIR package builder: the mapper's terminology + conformance release.

Roadmap P5 / hard rule: the NEMSIS codes this mapper emits must be registered
into fhirEngine so bound codes pass $validate-code. This module renders the
local clean NEMSIS registry (ADR-003 #5) and the authored maps/ artifacts as
an unpacked FHIR npm-style package — a flat directory of resource JSON files
plus a package.json manifest — which is exactly what fhirEngine's
`fhirengine-terminology install-ig <dir> <packageId>` consumes (and what a
release can tarball for distribution).

Contents:
  - CodeSystem-nemsis.json — every code in the registry, deduped across
    elements, content=fragment (we carry the mapped elements' codes, not the
    whole NEMSIS enumeration — a miss must stay resolvable, not invalid).
  - ValueSet-<element>.json per registry element — the per-element bindings,
    enumerated so fhirEngine can expand them without system semantics.
  - The authored ConceptMaps, StructureDefinitions (extension), and logical
    models copied verbatim from maps/.
"""

from __future__ import annotations

import json
import shutil
from importlib import metadata
from pathlib import Path

from .. import conformance
from . import registry, systems
from .conceptmaps import maps_dir

PACKAGE_NAME = "emsinterop.nemsis"
VALUESET_URL_BASE = conformance.CANONICAL_BASE + "/ValueSet/nemsis-"


def package_version() -> str:
    try:
        return metadata.version("emsinterop")
    except metadata.PackageNotFoundError:  # pragma: no cover
        return "0.0.0.dev0"


def nemsis_codesystem(version: str) -> dict:
    """The registry as one CodeSystem, codes deduped across elements (NEMSIS
    codes are globally scoped numbers; NV/PN codes recur under many elements
    with identical displays)."""
    concepts: dict[str, str | None] = {}
    for element_id, codes in registry.elements().items():
        for code, display in codes.items():
            if code == "__name__":
                continue
            concepts.setdefault(code, display)
    return {
        "resourceType": "CodeSystem",
        "id": "nemsis-registry",
        # OUR canonical, not the mPSC one. Codings keep pointing at
        # systems.NEMSIS (see below) so this project's data stays conformant
        # the day the IG is fixed — but publishing a definition AT that
        # canonical would assert we define it, and two conflicting definitions
        # of one identifier break whichever terminology server loads ours
        # second. Reference theirs; publish ours.
        "url": conformance.canonical("CodeSystem", "nemsis-registry"),
        "version": version,
        "name": "NEMSISRegistry",
        "title": "NEMSIS v3.5.0 concepts (emsInterop registry-derived)",
        "status": "active",
        "experimental": False,
        "content": "fragment",
        "description": (
            "Registry-derived NEMSIS v3.5.0 concepts, published under this "
            "project's own canonical. It MIRRORS the concepts expected at "
            f"{systems.NEMSIS}, which this project's resources reference in "
            "coding.system. As verified 2026-08-07 the mPSC build carries 18 "
            "placeholder concepts there (displays reading 'TODO: JFM', codes "
            "including 99270235, C7 and todo1), so it is not usable at "
            "runtime. This is not a CodeSystem supplement: it does not add "
            "designations to a working code system, it stands in for one that "
            "is not yet populated. It is retired when IHE publishes a usable "
            "NEMSIS CodeSystem — see conformance.GAPS['nemsis-codesystem-"
            "placeholders']."
        ),
        "identifier": [{"system": "urn:ietf:rfc:3986", "value": systems.NEMSIS}],
        "count": len(concepts),
        "concept": [
            {"code": code, **({"display": display} if display else {})}
            for code, display in sorted(concepts.items())
        ],
    }


def element_valueset(element_id: str, version: str) -> dict:
    codes = registry.elements()[element_id]
    name = codes.get("__name__")
    return {
        "resourceType": "ValueSet",
        "id": f"nemsis-{element_id.replace('.', '-')}",
        "url": f"{VALUESET_URL_BASE}{element_id}",
        "version": version,
        "name": f"Nemsis{element_id.replace('.', '')}",
        **({"title": f"NEMSIS {element_id} {name}"} if name else {}),
        "status": "active",
        "compose": {
            "include": [{
                "system": systems.NEMSIS,
                "concept": [
                    {"code": code, **({"display": display} if display else {})}
                    for code, display in sorted(codes.items())
                    if code != "__name__"
                ],
            }],
        },
    }


def build_package(out_dir: str | Path) -> dict:
    """Write the unpacked package; returns a summary of what was written."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    version = package_version()

    (out / "package.json").write_text(json.dumps({
        "name": PACKAGE_NAME,
        "version": version,
        "description": "NEMSIS v3.5.0 terminology + mapping conformance "
                       "artifacts from the emsInterop translation engine",
        "fhirVersions": ["4.0.1"],
        "dependencies": {"hl7.fhir.r4.core": "4.0.1"},
        # A machine-readable statement of what in this package is IHE's and
        # what is ours, so a consumer need not read our source to find out.
        # It rides in the MANIFEST, not as a sibling file: fhirEngine's
        # readPackageResources() parses every non-manifest file as a FHIR
        # resource, and this is not one.
        "emsinterop:conformance": conformance.summary(),
    }, indent=2) + "\n")

    cs = nemsis_codesystem(version)
    (out / "CodeSystem-nemsis-registry.json").write_text(
        json.dumps(cs, indent=2) + "\n")


    elements = sorted(registry.elements())
    for element_id in elements:
        vs = element_valueset(element_id, version)
        (out / f"ValueSet-{vs['id']}.json").write_text(
            json.dumps(vs, indent=2) + "\n")

    maps_root = maps_dir().parent
    copied = 0
    for subdir in ("conceptmaps", "structuredefinitions", "logical"):
        for source in sorted((maps_root / subdir).glob("*.json")):
            shutil.copyfile(source, out / source.name)
            copied += 1

    return {
        "package": PACKAGE_NAME,
        "version": version,
        "path": str(out),
        "codesystem_concepts": cs["count"],
        "valuesets": len(elements),
        "authored_artifacts": copied,
    }

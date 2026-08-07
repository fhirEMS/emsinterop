"""ConceptMap execution — lives in the mapper by design (fhirEngine has no $translate).

The authored FHIR ConceptMap resources in maps/conceptmaps/ are the spec
(upstream-contributable, CI-oracle-checked); this module executes them.

Dual-coding is the default (ADR-003): translate() callers combine the standard
target coding(s) with the original NEMSIS coding so nothing is lost.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from . import registry

_MAPS_ENV = "EMSINTEROP_MAPS_DIR"


def maps_dir() -> Path:
    """maps/conceptmaps directory: env override, else resolved from the repo layout."""
    if os.environ.get(_MAPS_ENV):
        return Path(os.environ[_MAPS_ENV])
    # src/emsinterop/terminology/conceptmaps.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3] / "maps" / "conceptmaps"


@lru_cache(maxsize=None)
def load(conceptmap_id: str) -> dict:
    path = maps_dir() / f"{conceptmap_id}.json"
    with open(path) as f:
        return json.load(f)


@lru_cache(maxsize=None)
def _index(conceptmap_id: str) -> dict[tuple[str, str], list[dict]]:
    """(target_system, source_code) -> list of target codings."""
    cm = load(conceptmap_id)
    idx: dict[tuple[str, str], list[dict]] = {}
    for group in cm.get("group", []):
        target_system = group.get("target")
        for element in group.get("element", []):
            targets = []
            for t in element.get("target", []):
                if t.get("equivalence") == "unmatched" or "code" not in t:
                    continue
                coding = {"system": target_system, "code": t["code"]}
                if t.get("display"):
                    coding["display"] = t["display"]
                targets.append(coding)
            idx.setdefault((target_system, element["code"]), []).extend(targets)
    return idx


def translate(conceptmap_id: str, code: str, target_system: str | None = None) -> list[dict]:
    """Standard-system codings for a NEMSIS code. Empty list if unmatched."""
    idx = _index(conceptmap_id)
    if target_system is not None:
        return list(idx.get((target_system, code), []))
    out: list[dict] = []
    for (_, src), codings in idx.items():
        if src == code:
            out.extend(codings)
    return out


def dual_code(
    element_id: str,
    code: str,
    conceptmap_id: str | None = None,
    target_system: str | None = None,
) -> dict:
    """CodeableConcept with standard coding(s) first and the original NEMSIS
    coding retained (dual-coding default, ADR-003). Works with no ConceptMap
    (NEMSIS-only coding) and with unmatched codes."""
    codings: list[dict] = []
    if conceptmap_id:
        codings.extend(translate(conceptmap_id, code, target_system))
    codings.append(registry.nemsis_coding(element_id, code))
    concept: dict = {"coding": codings}
    text = registry.display(element_id, code)
    if text:
        concept["text"] = text
    return concept

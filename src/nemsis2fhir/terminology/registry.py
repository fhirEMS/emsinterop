"""Local NEMSIS code registry — the clean, owned copy of the NEMSIS code system.

Extracted from the official NEMSIS 3.5.0 element enumeration tables (pinned
alongside the XSDs). We do NOT depend on the mPSC IG's CodeSystem at runtime
(it has TODO/placeholder concepts; ADR-003 #5), but we emit its canonical URL
so codings stay IG-conformant.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from . import systems


@lru_cache(maxsize=1)
def _codes() -> dict[str, dict[str, str]]:
    ref = resources.files("nemsis2fhir.terminology").joinpath("data/nemsis_codes.json")
    return json.loads(ref.read_text())


def display(element_id: str, code: str) -> str | None:
    """Official display text for a NEMSIS code, scoped by element id."""
    return _codes().get(element_id, {}).get(code)


def element_name(element_id: str) -> str | None:
    return _codes().get(element_id, {}).get("__name__")


def is_known(element_id: str, code: str) -> bool:
    return code in _codes().get(element_id, {})


def nemsis_coding(element_id: str, code: str) -> dict:
    """Coding in the (locally owned) NEMSIS code system."""
    coding: dict = {"system": systems.NEMSIS, "code": code}
    disp = display(element_id, code)
    if disp:
        coding["display"] = disp
    return coding

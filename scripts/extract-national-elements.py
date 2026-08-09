#!/usr/bin/env python3
"""Extract the NATIONAL NEMSIS element ids from the pinned XSD annotations.

NEMSIS marks each element <national>Yes|No</national>. This project maps the
NATIONAL set; state/local elements (national=No) are out of scope by design.
The coverage sweep needs that distinction so it stops reporting state elements
as unmapped coverage gaps. Regenerate after any XSD version bump:

    python scripts/extract-national-elements.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas" / "nemsis" / "3.5.0"
OUT = ROOT / "src" / "emsinterop" / "terminology" / "data" / "nemsis_national_elements.json"

PATTERN = re.compile(
    r"<number>([a-zA-Z]+\.\d+)</number>.*?<national>(Yes|No)</national>", re.S
)


def main() -> None:
    national: dict[str, str] = {}
    for xsd in sorted(SCHEMAS.glob("*.xsd")):
        for eid, flag in PATTERN.findall(xsd.read_text()):
            national.setdefault(eid, flag)
    yes = sorted(e for e, f in national.items() if f == "Yes")
    OUT.write_text(json.dumps({"version": "3.5.0", "national": yes}, indent=1) + "\n")
    print(f"{len(yes)} national of {len(national)} annotated elements -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

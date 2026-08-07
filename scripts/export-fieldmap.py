#!/usr/bin/env python3
"""Export the S2T workbook into the upstream contribution artifacts (P7).

The workbook (docs/02_NEMSIS35_to_FHIR_S2T_Mapping.xlsx) is the authored
spec; this renders its panel tabs as markdown tables + one combined CSV under
contrib/fieldmap/ — the completed NEMSIS->FHIR field map offered to the IHE
PCC mPSC IG (whose own table is ~90% empty). Reproducible: re-run after any
workbook edit; the outputs are generated, reviewed, and committed.

Usage: python scripts/export-fieldmap.py [workbook] [out_dir]
Requires the dev extra (openpyxl).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import openpyxl

PANEL_TABS = [
    "Admin_Org_Crew", "Encounter", "ePatient", "eSituation_eInjury", "eArrest",
    "eHistory", "eVitals", "eMedications", "eProcedures_eAirway",
    "eExam_eLabs_eDevice", "eDisposition", "ePayment", "eOutcome",
    "eNarrative_eOther",
]
CONTEXT_TABS = {"Coverage_Matrix": "coverage.md", "Terminology": "terminology.md"}


def _cell(value) -> str:
    return "" if value is None else str(value).replace("\n", " ").strip()


def _rows(worksheet):
    return [[_cell(c) for c in row] for row in worksheet.iter_rows(values_only=True)]


def _md_table(header: list[str], body: list[list[str]]) -> str:
    def esc(value: str) -> str:
        return value.replace("|", "\\|")

    width = len(header)
    lines = ["| " + " | ".join(esc(h) for h in header) + " |",
             "|" + "---|" * width]
    for row in body:
        row = (row + [""] * width)[:width]
        lines.append("| " + " | ".join(esc(v) for v in row) + " |")
    return "\n".join(lines)


def export(workbook_path: Path, out_dir: Path) -> dict:
    wb = openpyxl.load_workbook(workbook_path, read_only=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    combined: list[list[str]] = []
    combined_header: list[str] | None = None
    exported = 0

    for tab in PANEL_TABS:
        rows = _rows(wb[tab])
        title = rows[0][0] if rows and rows[0] else tab
        # Row 2 (index) is the column header on every panel tab.
        header, body = rows[2], [r for r in rows[3:] if any(r)]
        doc = (f"# {title}\n\n"
               f"Panel tab `{tab}` of the NEMSIS 3.5.0 → FHIR R4 source-to-target "
               f"workbook (emsInterop). Status column: Mapped = full target defined · "
               f"Seeded = target assigned · Deferred = intentionally postponed "
               f"(ledgered, never dropped).\n\n"
               + _md_table(header, body) + "\n")
        (out_dir / f"{tab}.md").write_text(doc)
        if combined_header is None:
            combined_header = ["Panel"] + header
        combined.extend([tab] + row for row in body)
        exported += len(body)

    with (out_dir / "nemsis-to-fhir-fieldmap.csv").open("w", newline="") as sink:
        writer = csv.writer(sink)
        writer.writerow(combined_header or [])
        writer.writerows(combined)

    for tab, filename in CONTEXT_TABS.items():
        rows = _rows(wb[tab])
        header, body = rows[2], [r for r in rows[3:] if any(r)]
        (out_dir / filename).write_text(
            f"# {rows[0][0] if rows and rows[0] else tab}\n\n"
            + _md_table(header, body) + "\n")

    return {"panels": len(PANEL_TABS), "rows": exported, "out": str(out_dir)}


if __name__ == "__main__":
    workbook = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "docs/02_NEMSIS35_to_FHIR_S2T_Mapping.xlsx")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("contrib/fieldmap")
    print(export(workbook, out))

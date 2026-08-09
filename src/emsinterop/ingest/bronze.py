"""Raw-NEMSIS bronze: the mapper's ONE Delta table (source audit/replay).

This is the only Delta table the mapper owns (ADR-009). It stores raw source
XML + metadata, one row per PatientCareReport — it never holds FHIR resources
(fhirEngine is the sole writer of FHIR storage).

Requires the optional `bronze` extra (deltalake); imported lazily so the core
mapper has no heavy dependencies.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

from . import safexml

from ..log import event, get_logger
from .parser import NEMSIS_NS, parse

logger = get_logger("bronze")


def land(xml_path: str | Path | bytes, table_path: str | Path) -> int:
    """Shred an EMSDataSet file (path, or raw bytes for in-flight documents
    like the push endpoint's) into the bronze table; returns rows written.

    Idempotent by file content: a file whose sha256 has already been landed is
    skipped (returns 0) — re-running an ingest sweep never duplicates audit
    rows, while a changed file (new hash) lands as new rows for replay."""
    try:
        import pyarrow as pa
        from deltalake import DeltaTable, write_deltalake
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(
            "raw-NEMSIS bronze requires the 'bronze' extra: pip install emsinterop[bronze]"
        ) from error

    raw = xml_path if isinstance(xml_path, bytes) else Path(xml_path).read_bytes()
    dataset = parse(raw)
    file_hash = hashlib.sha256(raw).hexdigest()
    try:
        table = DeltaTable(str(table_path))
        already = table.to_pyarrow_table(columns=["file_sha256"]).column("file_sha256")
        if file_hash in {str(v) for v in already}:
            event(logger, "bronze.deduped", table=table_path)
            return 0
    except Exception:
        pass  # table doesn't exist yet — first landing
    received_at = datetime.now(timezone.utc).isoformat()
    agency = dataset.header.value("dAgency.02")

    # One row per PatientCareReport, each stored as a SELF-CONTAINED
    # single-PCR EMSDataSet (its Header's DemographicGroup + any
    # eCustomConfiguration preserved) so replay feeds convert() directly.
    import copy as _copy

    root = safexml.fromstring(raw)
    pcr_nodes = root.findall(f".//{{{NEMSIS_NS}}}PatientCareReport")

    def single_pcr_document(pcr_node: etree._Element) -> str:
        source_header = pcr_node.getparent()
        single = etree.Element(root.tag, nsmap=root.nsmap)
        for name, value in root.attrib.items():
            single.set(name, value)
        header = etree.SubElement(single, f"{{{NEMSIS_NS}}}Header")
        for child in source_header:
            if child.tag == f"{{{NEMSIS_NS}}}PatientCareReport":
                continue
            header.append(_copy.deepcopy(child))
        header.append(_copy.deepcopy(pcr_node))
        return etree.tostring(single, encoding="unicode")

    rows = {
        "pcr_number": [],
        "pcr_uuid": [],
        "agency_number": [],
        "nemsis_version": [],
        "file_sha256": [],
        "received_at": [],
        "raw_xml": [],
    }
    for pcr, node in zip(dataset.reports, pcr_nodes):
        rows["pcr_number"].append(pcr.pcr_number)
        rows["pcr_uuid"].append(pcr.uuid)
        rows["agency_number"].append(agency)
        rows["nemsis_version"].append(dataset.nemsis_version)
        rows["file_sha256"].append(file_hash)
        rows["received_at"].append(received_at)
        rows["raw_xml"].append(single_pcr_document(node))

    write_deltalake(str(table_path), pa.table(rows), mode="append")
    event(logger, "bronze.landed", rows=len(dataset.reports),
          agency_number=agency, table=table_path)
    return len(dataset.reports)


def replay(table_path: str | Path, pcr_number: str | None = None) -> list[bytes]:
    """Raw PCR XML back out of bronze — the replay half of audit/replay.

    Each returned payload is a self-contained EMSDataSet (original header +
    the stored PatientCareReport) so it feeds straight back into convert()."""
    try:
        from deltalake import DeltaTable
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(
            "raw-NEMSIS bronze requires the 'bronze' extra: pip install emsinterop[bronze]"
        ) from error

    table = DeltaTable(str(table_path)).to_pyarrow_table(
        columns=["pcr_number", "raw_xml"]
    )
    out: list[bytes] = []
    for row_pcr, raw_xml in zip(
        table.column("pcr_number").to_pylist(), table.column("raw_xml").to_pylist()
    ):
        if pcr_number is not None and row_pcr != pcr_number:
            continue
        out.append(raw_xml.encode() if isinstance(raw_xml, str) else raw_xml)
    return out

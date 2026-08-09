"""NEMSIS EMSDataSet XML -> intermediate model.

Generic recursive walk: an element with element children is a NemsisGroup, a
leaf is a NemsisElement. NV/PN/CorrelationID/UUID attributes and xsi:nil are
lifted into first-class model fields — nil elements are always kept.
"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from . import safexml

from ..model import (
    DemographicHeader,
    EMSDataSet,
    NemsisElement,
    NemsisGroup,
    PatientCareReport,
)

NEMSIS_NS = "http://www.nemsis.org"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_NIL = f"{{{XSI_NS}}}nil"
_VERSION_RE = re.compile(r"(3\.\d+\.\d+(?:\.[A-Za-z0-9]+)*)")


def _local(tag) -> str:
    return etree.QName(tag).localname


def _leaf_text(node: etree._Element) -> str | None:
    """The element's text content, including text that follows a comment.

    lxml splits character data around comments: in
    `<eVitals.06><!-- recalibrated -->124</eVitals.06>` the `124` is the
    COMMENT's `.tail`, not the element's `.text`, so reading `.text` alone
    returns None and the reading is lost without a ledger entry. Join the
    element's own text with every child's tail to recover it."""
    parts = [node.text or ""]
    parts.extend(child.tail or "" for child in node)
    text = "".join(parts).strip()
    return text or None


def _parse_leaf(node: etree._Element) -> NemsisElement:
    attrs: dict[str, str] = {}
    nv = pn = correlation = None
    nil = node.get(_NIL) in ("true", "1")
    for name, val in node.attrib.items():
        local = _local(name) if name.startswith("{") else name
        if local == "nil":
            continue
        if local == "NV":
            nv = val
        elif local == "PN":
            pn = val
        elif local == "CorrelationID":
            correlation = val
        else:
            attrs[local] = val
    text = None if nil else _leaf_text(node)
    return NemsisElement(
        element_id=_local(node.tag),
        value=text,
        nil=nil,
        nv=nv,
        pn=pn,
        correlation_id=correlation,
        attributes=attrs,
    )


def _is_group(node: etree._Element, tag: str) -> bool:
    """Container or leaf?

    NOT `len(node) > 0` — lxml's len() counts comments and PIs, so
    `<eVitals.06><!-- recalibrated -->120</eVitals.06>` would be read as an
    empty group and the reading would vanish with no ledger entry, silently
    breaking the never-silently-drop rule. Count ELEMENT children only.

    The `Group` suffix is the backstop for the converse case, an empty
    container like `<eVitals.VitalGroup/>`, which has no element children but
    is still a group. The convention is total across the pinned 3.5.0 schemas:
    every container element's name ends in `Group`, and no leaf's does.
    """
    if tag.endswith("Group"):
        return True
    return any(isinstance(child.tag, str) for child in node)


def _parse_group(node: etree._Element, index: int = 0) -> NemsisGroup:
    group = NemsisGroup(
        tag=_local(node.tag),
        index=index,
        correlation_id=node.get("CorrelationID"),
        uuid=node.get("UUID"),
    )
    counts: dict[str, int] = {}
    for child in node:
        if not isinstance(child.tag, str):
            continue  # comments / PIs
        tag = _local(child.tag)
        if _is_group(child, tag):
            counts[tag] = counts.get(tag, 0) + 1
            group.groups.append(_parse_group(child, counts[tag] - 1))
        else:
            group.add(_parse_leaf(child))
    return group


def _detect_version(root: etree._Element) -> str | None:
    loc = root.get(f"{{{XSI_NS}}}schemaLocation")
    if loc:
        m = _VERSION_RE.search(loc)
        if m:
            return m.group(1)
    return None


def parse(source: str | Path | bytes) -> EMSDataSet:
    """Parse an EMSDataSet document from a path or raw bytes."""
    if isinstance(source, bytes):
        root = safexml.fromstring(source)
    else:
        root = safexml.parse(source).getroot()
    if _local(root.tag) != "EMSDataSet":
        raise ValueError(f"Expected EMSDataSet root, got {_local(root.tag)}")

    header = DemographicHeader()
    reports: list[PatientCareReport] = []
    for header_node in root:
        if not isinstance(header_node.tag, str) or _local(header_node.tag) != "Header":
            continue
        for child in header_node:
            if not isinstance(child.tag, str):
                continue
            tag = _local(child.tag)
            if tag == "DemographicGroup":
                header.agency = _parse_group(child)
            elif tag == "PatientCareReport":
                pcr = PatientCareReport(uuid=child.get("UUID"))
                for section_node in child:
                    if not isinstance(section_node.tag, str):
                        continue
                    section = _parse_group(section_node)
                    pcr.sections[section.tag] = section
                reports.append(pcr)

    return EMSDataSet(header=header, reports=reports, nemsis_version=_detect_version(root))

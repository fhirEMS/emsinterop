"""DEMDataSet (demographics) ingest — the agency/facility roster.

The EMSDataSet header carries only dAgency.01/.02/.04; the agency NAME
(dAgency.03) lives in the NEMSIS DEMDataSet, whose shape is:

    DEMDataSet
      dCustomConfiguration?          (0..1)
      DemographicReport              (1..*)
        dRecord?                     (software info, 0..1)
        dAgency                      (REQUIRED: .01 state id, .02 number,
                                      .03 name [0..1, nillable NV],
                                      .04 state, service groups, licensure...)
        dContact? dConfiguration dLocation? dVehicle? dPersonnel? dDevice?
        dFacility?                   (dFacilityGroup* -> FacilityGroup* ->
                                      dFacility.02 name / .03 code)

This module extracts lookup dicts that plug straight into
``convert(..., agency_names=...)`` so the Organization can carry its US Core
required ``name`` (see mapping/agency.py and the seeded dAgency.03 issue).

NV-nilled dAgency.03 (7701xxx) is honestly absent — a nil name never produces
a dict entry (the mapper keeps its data-absent-reason path); it is *not*
silently treated as an empty string.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from . import safexml

from .xsd import PINNED_VERSION, validate_dataset

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_NIL = f"{{{XSI_NS}}}nil"


def _local(tag) -> str:
    return etree.QName(tag).localname


def _parse(source: str | Path | bytes) -> etree._Element:
    if isinstance(source, bytes):
        return safexml.fromstring(source)
    return safexml.parse(source).getroot()


def _text(node: etree._Element) -> str | None:
    """Element text, honoring xsi:nil (NV-nilled values are absent, not '')."""
    if node.get(_NIL) in ("true", "1"):
        return None
    if node.text and node.text.strip():
        return node.text.strip()
    return None


def _leaf_map(root: etree._Element, section: str, key_tags: tuple[str, ...], value_tag: str) -> dict[str, str]:
    """Within each <section>, map every key element's text -> the value element's text."""
    out: dict[str, str] = {}
    for node in root.iter():
        if not isinstance(node.tag, str) or _local(node.tag) != section:
            continue
        keys: list[str] = []
        value: str | None = None
        for leaf in node.iter():
            if not isinstance(leaf.tag, str):
                continue
            tag = _local(leaf.tag)
            if tag in key_tags:
                text = _text(leaf)
                if text:
                    keys.append(text)
            elif tag == value_tag:
                value = value or _text(leaf)
        if value:
            for key in keys:
                out[key] = value
    return out


def validate_dem(source: str | Path | bytes, version: str = PINNED_VERSION) -> list[str]:
    """XSD-validate a DEMDataSet document; returns error strings (empty = valid).

    Same contract as ingest.xsd.validate() for the EMSDataSet — pair with
    to_operation_outcome() for the machine-readable quarantine record.
    """
    return validate_dataset(source, "DEMDataSet", version)


def agency_names(source: str | Path | bytes) -> dict[str, str]:
    """dAgency.01 (state id) AND dAgency.02 (number) -> dAgency.03 (agency name).

    Both identifiers key the same name so the result is directly usable as
    convert(..., agency_names=agency_names(dem_path)) regardless of which
    identifier the EMSDataSet header carries. Agencies with a nil/absent
    dAgency.03 contribute no entries.
    """
    return _leaf_map(_parse(source), "dAgency", ("dAgency.01", "dAgency.02"), "dAgency.03")


def personnel_names(source: str | Path | bytes) -> dict[str, dict[str, str]]:
    """dPersonnel.23 (state licensure id) -> {"family": ..., "given": ...}.

    NEMSIS names this join itself: `eCrew.01` is defined as "The state
    certification/licensure ID number assigned to the crew member", and
    `dPersonnel.23` is "EMS Personnel's State's Licensure ID Number". A PCR
    therefore identifies its crew by licensure number and carries no names at
    all — exactly as it carries an agency number and no agency name.

    Without this the Practitioner resources are anonymous: correct, joined,
    and unable to tell a receiving clinician who ran the call.
    """
    out: dict[str, dict[str, str]] = {}
    for group in _parse(source).iter():
        if _local(group.tag) != "dPersonnel.PersonnelGroup":
            continue
        fields = {_local(e.tag): _text(e) for e in group.iter()}
        licence = fields.get("dPersonnel.23")
        if not licence:
            continue  # a roster entry with no licence id joins to nothing
        entry = {}
        if fields.get("dPersonnel.01"):
            entry["family"] = fields["dPersonnel.01"]
        if fields.get("dPersonnel.02"):
            entry["given"] = fields["dPersonnel.02"]
        # Contact detail rides along: C-CDA's US Realm Header makes telecom and
        # address SHALL on the document author, and this is where NEMSIS keeps
        # them. Absent fields stay absent — never invented downstream.
        if fields.get("dPersonnel.09"):
            entry["phone"] = fields["dPersonnel.09"]
        address = {
            "line": fields.get("dPersonnel.04"),
            "city": fields.get("dPersonnel.05"),      # GNIS code, not a name
            "state": fields.get("dPersonnel.06"),     # ANSI code
            "postalCode": fields.get("dPersonnel.07"),
        }
        address = {k: v for k, v in address.items() if v}
        if address:
            entry["address"] = address
        if entry:
            out[licence] = entry
    return out


def agency_contact(source: str | Path | bytes) -> dict[str, str]:
    """dContact telecom/address for the agency — the CDA custodian's details.

    One contact per roster; the first with a phone or address wins."""
    for group in _parse(source).iter():
        if _local(group.tag) != "dContact":
            continue
        fields = {_local(e.tag): _text(e) for e in group.iter()}
        out = {
            "phone": fields.get("dContact.10"),
            "email": fields.get("dContact.11"),
            "line": fields.get("dContact.05"),
            "city": fields.get("dContact.06"),
            "state": fields.get("dContact.07"),
            "postalCode": fields.get("dContact.08"),
        }
        out = {k: v for k, v in out.items() if v}
        if out:
            return out
    return {}


def facility_names(source: str | Path | bytes) -> dict[str, str]:
    """dFacility.03 (facility code) -> dFacility.02 (facility name).

    Scoped per dFacility.FacilityGroup instance (one facility each).
    """
    return _leaf_map(_parse(source), "dFacility.FacilityGroup", ("dFacility.03",), "dFacility.02")

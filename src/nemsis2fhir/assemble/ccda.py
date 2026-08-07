"""C-CDA projection — the second thin document projection over Layer A.

Renders the canonical in-memory graph (the SAME MappingContext the mPSC
document projects from — no read-back, §5.5a) as a C-CDA R2.1 Continuity of
Care Document. The mPSC IG is the FHIR-era successor of the IHE Paramedicine
Care Summary CDA supplement, so the section models are siblings; this module
targets the C-CDA R2.1 base templates (stable OIDs, hospital-consumable) with
the template table parameterized so PCS supplement templateIds can be layered
on once pinned (see TEMPLATES).

NV/PN land in their native CDA idioms: NV -> nullFlavor (NA/UNK/MSK),
PN -> negationInd="true" (medication-not-given, procedure-not-done, NKDA).

Scope notes (v1, tracked in README):
- structural conformance + corpus tests; the schematron validation tier
  (ONC C-CDA validator, Java/CI like our other oracles) is the follow-up.
- routeCode carries SNOMED (C-CDA prefers NCI Thesaurus routes — a
  ConceptMap-sized gap shared with the FHIR side).
- NEMSIS original codes are not yet carried as CDA <translation> elements.
"""

from __future__ import annotations

from lxml import etree

from ..mapping.context import MappingContext
from ..terminology import nv_pn, registry

NS = "urn:hl7-org:v3"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
E = "{%s}" % NS

# OIDs
OID_LOINC = "2.16.840.1.113883.6.1"
OID_SNOMED = "2.16.840.1.113883.6.96"
OID_RXNORM = "2.16.840.1.113883.6.88"
OID_ICD10CM = "2.16.840.1.113883.6.90"
OID_CONFIDENTIALITY = "2.16.840.1.113883.5.25"
OID_ADMIN_GENDER = "2.16.840.1.113883.5.1"
OID_NEMSIS_ROOT = "2.16.840.1.113883.3.10.100"  # placeholder root for NEMSIS ids (document + revisit)

# C-CDA R2.1 template ids (base). PCS supplement ids can be appended per key
# once pinned from the IHE PCS CDA supplement.
TEMPLATES: dict[str, list[tuple[str, str | None]]] = {
    "us_realm_header": [("2.16.840.1.113883.10.20.22.1.1", "2015-08-01")],
    "ccd_document": [("2.16.840.1.113883.10.20.22.1.2", "2015-08-01")],
    "problems_section": [("2.16.840.1.113883.10.20.22.2.5.1", "2015-08-01")],
    "problem_concern": [("2.16.840.1.113883.10.20.22.4.3", "2015-08-01")],
    "problem_observation": [("2.16.840.1.113883.10.20.22.4.4", "2015-08-01")],
    "allergies_section": [("2.16.840.1.113883.10.20.22.2.6.1", "2015-08-01")],
    "allergy_concern": [("2.16.840.1.113883.10.20.22.4.30", "2015-08-01")],
    "allergy_observation": [("2.16.840.1.113883.10.20.22.4.7", "2014-06-09")],
    "medications_section": [("2.16.840.1.113883.10.20.22.2.1.1", "2014-06-09")],
    "medication_activity": [("2.16.840.1.113883.10.20.22.4.16", "2014-06-09")],
    "vitals_section": [("2.16.840.1.113883.10.20.22.2.4.1", "2015-08-01")],
    "vitals_organizer": [("2.16.840.1.113883.10.20.22.4.26", "2015-08-01")],
    "vital_observation": [("2.16.840.1.113883.10.20.22.4.27", "2014-06-09")],
    "procedures_section": [("2.16.840.1.113883.10.20.22.2.7.1", "2014-06-09")],
    "procedure_activity": [("2.16.840.1.113883.10.20.22.4.14", "2014-06-09")],
}


def _ts(iso: str | None) -> str | None:
    """ISO 8601 -> CDA TS (YYYYMMDDHHMMSS±ZZZZ)."""
    if not iso:
        return None
    return (
        iso.replace("-", "", 2).replace(":", "").replace("T", "")
        .replace("-", "-").replace("+", "+")
    )


def _el(parent, tag: str, **attrs) -> etree._Element:
    node = etree.SubElement(parent, f"{E}{tag}")
    for name, value in attrs.items():
        if value is not None:
            node.set(name.rstrip("_"), value)
    return node


def _template_ids(parent, key: str) -> None:
    for root, extension in TEMPLATES[key]:
        attrs = {"root": root}
        if extension:
            attrs["extension"] = extension
        _el(parent, "templateId", **attrs)


def _code(parent, tag, code, system_oid, display=None, system_name=None) -> etree._Element:
    return _el(parent, tag, code=code, codeSystem=system_oid,
               displayName=display, codeSystemName=system_name)


def _nullflavor_value(parent, tag: str, nv: str | None, xsi_type: str | None = None):
    node = _el(parent, tag, nullFlavor=nv_pn.nullflavor(nv))
    if xsi_type:
        node.set(f"{{{XSI}}}type", xsi_type)
    return node


def _narrative(section, lines: list[str]) -> None:
    text = _el(section, "text")
    if not lines:
        _el(text, "paragraph").text = "No information reported."
        return
    lst = _el(text, "list")
    for line in lines:
        _el(lst, "item").text = line


class CcdaRenderer:
    """Renders one MappingContext to a ClinicalDocument element tree."""

    def __init__(self, ctx: MappingContext):
        self.ctx = ctx
        self.pcr = ctx.pcr

    # ---- header ------------------------------------------------------------

    def render(self) -> etree._Element:
        doc = etree.Element(f"{E}ClinicalDocument", nsmap={None: NS, "xsi": XSI})
        _el(doc, "realmCode", code="US")
        _el(doc, "typeId", root="2.16.840.1.113883.1.3", extension="POCD_HD000040")
        _template_ids(doc, "us_realm_header")
        _template_ids(doc, "ccd_document")
        _el(doc, "id", root=self.ctx.rid("ccda-document"))
        # CCD document code is fixed; the EMS PCR type rides as translation.
        code = _code(doc, "code", "34133-9", OID_LOINC,
                     "Summarization of Episode Note", "LOINC")
        _code(code, "translation", "67796-3", OID_LOINC,
              "EMS patient care report", "LOINC")
        _el(doc, "title").text = "EMS Patient Care Summary"
        transfer = self.pcr.value("eTimes.12") or self.pcr.value("eTimes.11")
        _el(doc, "effectiveTime", value=_ts(transfer))
        confidentiality = "R" if self._restricted() else "N"
        _el(doc, "confidentialityCode", code=confidentiality,
            codeSystem=OID_CONFIDENTIALITY)
        _el(doc, "languageCode", code="en-US")
        self._record_target(doc)
        self._author(doc)
        self._custodian(doc)
        self._encompassing_encounter(doc)
        body = _el(_el(_el(doc, "component"), "structuredBody"), "component")
        # Each section gets its own component under structuredBody.
        structured_body = body.getparent()
        body.getparent().remove(body)
        for build in (self._problems_section, self._allergies_section,
                      self._medications_section, self._vitals_section,
                      self._procedures_section):
            component = _el(structured_body, "component")
            component.append(build())
        return doc

    def _restricted(self) -> bool:
        return any(
            coding.get("code") == "R"
            for resource in self.ctx.resources
            for coding in resource.get("meta", {}).get("security", [])
        )

    def _record_target(self, doc) -> None:
        role = _el(_el(doc, "recordTarget"), "patientRole")
        patient_id = self.pcr.value("ePatient.01")
        if patient_id:
            _el(role, "id", root=OID_NEMSIS_ROOT, extension=patient_id)
        else:
            _el(role, "id", nullFlavor="UNK")
        addr = _el(role, "addr", use="H")
        street = self.pcr.value("ePatient.05")
        if street:
            _el(addr, "streetAddressLine").text = street
        for element_id, tag in (("ePatient.06", "city"), ("ePatient.08", "state"),
                                ("ePatient.09", "postalCode")):
            value = self.pcr.value(element_id)
            if value:
                _el(addr, tag).text = value
        phone = self.pcr.value("ePatient.18")
        _el(role, "telecom", **({"value": f"tel:{phone}"} if phone else {"nullFlavor": "UNK"}))
        patient = _el(role, "patient")
        name = _el(patient, "name", use="L")
        given = self.pcr.value("ePatient.03")
        family = self.pcr.value("ePatient.02")
        if given:
            _el(name, "given").text = given
        if family:
            _el(name, "family").text = family
        sex = self.pcr.first("ePatient.25")
        gender = {"9919001": "F", "9919003": "M"}.get(sex.value if sex and sex.has_value else "")
        if gender:
            _el(patient, "administrativeGenderCode", code=gender, codeSystem=OID_ADMIN_GENDER)
        else:
            _el(patient, "administrativeGenderCode",
                nullFlavor=nv_pn.nullflavor(sex.nv if sex else None))
        dob = self.pcr.first("ePatient.17")
        if dob is not None and dob.has_value:
            _el(patient, "birthTime", value=dob.value.replace("-", ""))
        else:
            _el(patient, "birthTime", nullFlavor=nv_pn.nullflavor(dob.nv if dob else None))

    def _agency_org(self, parent) -> None:
        org = _el(parent, "representedOrganization")
        number = self.ctx.header.value("dAgency.02")
        _el(org, "id", root=OID_NEMSIS_ROOT, extension=number or "unknown")
        name = self.ctx.agency_names.get(number or "")
        if name:
            _el(org, "name").text = name

    def _author(self, doc) -> None:
        author = _el(doc, "author")
        _el(author, "time", value=_ts(self.pcr.value("eTimes.12")))
        assigned = _el(author, "assignedAuthor")
        _el(assigned, "id", root=OID_NEMSIS_ROOT,
            extension=self.ctx.header.value("dAgency.02") or "unknown")
        device = _el(assigned, "assignedAuthoringDevice")
        _el(device, "manufacturerModelName").text = self.pcr.value("eRecord.02") or "unknown"
        _el(device, "softwareName").text = (
            f"{self.pcr.value('eRecord.03') or 'ePCR'} via nemsis2fhir"
        )
        self._agency_org(assigned)

    def _custodian(self, doc) -> None:
        assigned = _el(_el(doc, "custodian"), "assignedCustodian")
        org = _el(assigned, "representedCustodianOrganization")
        number = self.ctx.header.value("dAgency.02")
        _el(org, "id", root=OID_NEMSIS_ROOT, extension=number or "unknown")
        name = self.ctx.agency_names.get(number or "")
        _el(org, "name").text = name or f"EMS Agency {number or ''}".strip()

    def _encompassing_encounter(self, doc) -> None:
        encounter = _el(_el(doc, "componentOf"), "encompassingEncounter")
        incident = self.pcr.value("eResponse.03")
        _el(encounter, "id", root=OID_NEMSIS_ROOT, extension=incident or "unknown")
        time = _el(encounter, "effectiveTime")
        _el(time, "low", value=_ts(self.pcr.value("eTimes.06") or self.pcr.value("eTimes.03")))
        _el(time, "high", value=_ts(self.pcr.value("eTimes.12") or self.pcr.value("eTimes.11")))

    # ---- sections ----------------------------------------------------------

    def _section(self, key: str, loinc: str, title: str) -> etree._Element:
        section = etree.Element(f"{E}section")
        _template_ids(section, key)
        _code(section, "code", loinc, OID_LOINC, title, "LOINC")
        _el(section, "title").text = title
        return section

    def _problems_section(self) -> etree._Element:
        section = self._section("problems_section", "11450-4", "Problems")
        conditions = [r for r in self.ctx.resources if r["resourceType"] == "Condition"]
        _narrative(section, [
            c["code"].get("text") or (c["code"].get("coding") or [{}])[0].get("code", "")
            for c in conditions
        ])
        for condition in conditions:
            act = _el(_el(section, "entry"), "act", classCode="ACT", moodCode="EVN")
            _template_ids(act, "problem_concern")
            _el(act, "id", root=condition["id"])
            _code(act, "code", "CONC", "2.16.840.1.113883.5.6")
            _el(act, "statusCode", code="active")
            observation = _el(_el(act, "entryRelationship", typeCode="SUBJ"),
                              "observation", classCode="OBS", moodCode="EVN")
            _template_ids(observation, "problem_observation")
            _el(observation, "id", root=self.ctx.rid("ccda-problem", condition["id"]))
            _code(observation, "code", "55607006", OID_SNOMED, "Problem", "SNOMED CT")
            _el(observation, "statusCode", code="completed")
            if condition.get("onsetDateTime"):
                _el(_el(observation, "effectiveTime"), "low",
                    value=_ts(condition["onsetDateTime"]))
            icd = next((c for c in condition["code"].get("coding", [])
                        if c.get("system", "").endswith("icd-10-cm")), None)
            if icd:
                value = _el(observation, "value", code=icd["code"], codeSystem=OID_ICD10CM,
                            codeSystemName="ICD-10-CM")
                value.set(f"{{{XSI}}}type", "CD")
            else:
                value = _nullflavor_value(observation, "value", None, "CD")
                text = condition["code"].get("text")
                if text:
                    _el(value, "originalText").text = text
        return section

    def _allergies_section(self) -> etree._Element:
        section = self._section("allergies_section", "48765-2", "Allergies and Intolerances")
        allergies = [r for r in self.ctx.resources if r["resourceType"] == "AllergyIntolerance"]
        _narrative(section, [a["code"].get("text") or "coded allergy" for a in allergies])
        for allergy in allergies:
            act = _el(_el(section, "entry"), "act", classCode="ACT", moodCode="EVN")
            _template_ids(act, "allergy_concern")
            _el(act, "id", root=allergy["id"])
            _code(act, "code", "CONC", "2.16.840.1.113883.5.6")
            _el(act, "statusCode", code="active")
            nkda = any(c.get("code") == "409137002" for c in allergy["code"].get("coding", []))
            observation = _el(_el(act, "entryRelationship", typeCode="SUBJ"),
                              "observation", classCode="OBS", moodCode="EVN",
                              negationInd="true" if nkda else None)
            _template_ids(observation, "allergy_observation")
            _el(observation, "id", root=self.ctx.rid("ccda-allergy", allergy["id"]))
            _code(observation, "code", "ASSERTION", "2.16.840.1.113883.5.4")
            _el(observation, "statusCode", code="completed")
            # NKDA: negated drug-allergy assertion — CDA's native pertinent-negative.
            value = _el(observation, "value", code="416098002", codeSystem=OID_SNOMED,
                        displayName="Drug allergy", codeSystemName="SNOMED CT")
            value.set(f"{{{XSI}}}type", "CD")
            if not nkda:
                rx = next((c for c in allergy["code"].get("coding", [])
                           if c.get("system", "").endswith("rxnorm")), None)
                participant = _el(_el(observation, "participant", typeCode="CSM"),
                                  "participantRole", classCode="MANU")
                entity = _el(participant, "playingEntity", classCode="MMAT")
                if rx:
                    _code(entity, "code", rx["code"], OID_RXNORM, None, "RxNorm")
                else:
                    _el(entity, "code", nullFlavor="UNK")
        return section

    def _medications_section(self) -> etree._Element:
        section = self._section("medications_section", "10160-0", "Medications")
        admins = [r for r in self.ctx.resources
                  if r["resourceType"] == "MedicationAdministration"]
        _narrative(section, [
            (a.get("medicationCodeableConcept") or {}).get("text")
            or (a.get("medicationCodeableConcept") or {}).get("coding", [{}])[0].get("code", "")
            for a in admins
        ])
        for admin in admins:
            negated = admin.get("status") == "not-done"
            substance = _el(_el(section, "entry"), "substanceAdministration",
                            classCode="SBADM", moodCode="EVN",
                            negationInd="true" if negated else None)
            _template_ids(substance, "medication_activity")
            _el(substance, "id", root=admin["id"])
            _el(substance, "statusCode", code="completed")
            when = admin.get("effectiveDateTime")
            time = _el(substance, "effectiveTime")
            time.set(f"{{{XSI}}}type", "IVL_TS")
            if when:
                _el(time, "low", value=_ts(when))
            else:
                time.set("nullFlavor", "UNK")
            dose_value = (admin.get("dosage") or {}).get("dose", {}).get("value")
            if dose_value is not None:
                _el(substance, "doseQuantity", value=str(dose_value))
            material = _el(_el(_el(substance, "consumable"), "manufacturedProduct",
                               classCode="MANU"), "manufacturedMaterial")
            rx = next((c for c in (admin.get("medicationCodeableConcept") or {})
                       .get("coding", []) if c.get("system", "").endswith("rxnorm")), None)
            if rx:
                _code(material, "code", rx["code"], OID_RXNORM, None, "RxNorm")
            else:
                code = _el(material, "code", nullFlavor="NA" if negated else "UNK")
                reason = (admin.get("statusReason") or [{}])
                text = (reason[0] if isinstance(reason, list) else reason).get("text")
                if text:
                    _el(code, "originalText").text = text
        return section

    def _vitals_section(self) -> etree._Element:
        section = self._section("vitals_section", "8716-3", "Vital Signs")
        vitals = [
            r for r in self.ctx.resources
            if r["resourceType"] == "Observation"
            and any(c.get("code") == "vital-signs"
                    for cat in r.get("category", []) for c in cat.get("coding", []))
        ]
        by_time: dict[str, list[dict]] = {}
        for obs in vitals:
            by_time.setdefault(obs.get("effectiveDateTime", ""), []).append(obs)
        _narrative(section, [f"Vital signs at {t or 'unknown time'}" for t in sorted(by_time)])
        for when in sorted(by_time):
            organizer = _el(_el(section, "entry"), "organizer",
                            classCode="CLUSTER", moodCode="EVN")
            _template_ids(organizer, "vitals_organizer")
            _el(organizer, "id", root=self.ctx.rid("ccda-vitals", when))
            _code(organizer, "code", "46680005", OID_SNOMED, "Vital signs", "SNOMED CT")
            _el(organizer, "statusCode", code="completed")
            _el(organizer, "effectiveTime", value=_ts(when or None),
                **({} if when else {"nullFlavor": "UNK"}))
            for obs in by_time[when]:
                self._vital_components(organizer, obs)
        return section

    def _vital_components(self, organizer, obs: dict) -> None:
        loinc = next((c for c in obs.get("code", {}).get("coding", [])
                      if c.get("system") == "http://loinc.org"), None)
        components = obs.get("component") or [obs]
        for comp in components:
            comp_loinc = next((c for c in comp.get("code", {}).get("coding", [])
                               if c.get("system") == "http://loinc.org"), loinc)
            if comp_loinc is None:
                continue
            observation = _el(_el(organizer, "component"), "observation",
                              classCode="OBS", moodCode="EVN")
            _template_ids(observation, "vital_observation")
            _el(observation, "id",
                root=self.ctx.rid("ccda-vital", obs["id"], comp_loinc["code"]))
            _code(observation, "code", comp_loinc["code"], OID_LOINC,
                  comp_loinc.get("display"), "LOINC")
            _el(observation, "statusCode", code="completed")
            _el(observation, "effectiveTime", value=_ts(obs.get("effectiveDateTime")))
            quantity = comp.get("valueQuantity")
            if quantity:
                value = _el(observation, "value", value=str(quantity["value"]),
                            unit=quantity.get("code") or quantity.get("unit"))
                value.set(f"{{{XSI}}}type", "PQ")
            else:
                dar = (comp.get("dataAbsentReason") or {}).get("coding", [])
                nemsis_nv = next((c["code"] for c in dar
                                  if c.get("system", "").endswith("/NEMSIS")), None)
                _nullflavor_value(observation, "value", nemsis_nv, "PQ")

    def _procedures_section(self) -> etree._Element:
        section = self._section("procedures_section", "47519-4", "Procedures")
        procedures = [r for r in self.ctx.resources if r["resourceType"] == "Procedure"]
        _narrative(section, [
            p["code"].get("text") or (p["code"].get("coding") or [{}])[0].get("code", "")
            for p in procedures
        ])
        for procedure in procedures:
            negated = procedure.get("status") == "not-done"
            activity = _el(_el(section, "entry"), "procedure",
                           classCode="PROC", moodCode="EVN",
                           negationInd="true" if negated else None)
            _template_ids(activity, "procedure_activity")
            _el(activity, "id", root=procedure["id"])
            snomed = next((c for c in procedure["code"].get("coding", [])
                           if c.get("system", "").endswith("snomed.info/sct")), None)
            if snomed:
                _code(activity, "code", snomed["code"], OID_SNOMED, None, "SNOMED CT")
            else:
                code = _el(activity, "code", nullFlavor="NA" if negated else "UNK")
                text = procedure["code"].get("text")
                if text:
                    _el(code, "originalText").text = text
            _el(activity, "statusCode", code="completed")
            if procedure.get("performedDateTime"):
                _el(activity, "effectiveTime", value=_ts(procedure["performedDateTime"]))
        return section


def render_ccda(ctx: MappingContext) -> bytes:
    """The C-CDA document as serialized XML."""
    doc = CcdaRenderer(ctx).render()
    return etree.tostring(doc, pretty_print=True, xml_declaration=True, encoding="UTF-8")

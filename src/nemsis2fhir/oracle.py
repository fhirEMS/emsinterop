"""CI fidelity oracle support (ADR-002).

Exports panel sections of the parsed intermediate model as instances of the
logical models in maps/logical/, so the reference Java FML engine
(validator_cli / Matchbox — CI only, never production) can execute the authored
StructureMaps on the same input the native Python mappers consume.
"""

from __future__ import annotations

from .model import PatientCareReport

_EPATIENT_SINGLE = [
    "ePatient.01", "ePatient.02", "ePatient.03", "ePatient.04", "ePatient.05",
    "ePatient.06", "ePatient.07", "ePatient.08", "ePatient.09", "ePatient.10",
    "ePatient.15", "ePatient.16", "ePatient.17", "ePatient.25",
]
_EPATIENT_REPEATING = ["ePatient.14", "ePatient.18", "ePatient.19"]


def patient_oracle_projection(patient: dict) -> dict:
    """The map-covered surface of a Patient, for oracle comparison.

    The native Python mapper enriches beyond the declarative map (dual-coded
    race extensions, temp/resource-id identifiers, meta.profile, NV/PN
    handling — the typed-helper layer of Architecture §9); the oracle asserts
    the shared declarative core is IDENTICAL between the reference engine's
    output and ours.
    """
    projection: dict = {}
    agency_ids = [
        {"system": i.get("system"), "value": i.get("value"), "use": i.get("use")}
        for i in patient.get("identifier", [])
        if i.get("system") == "urn:nemsis:identifier:patient"
    ]
    if agency_ids:
        projection["identifier"] = agency_ids
    names = [
        {k: n[k] for k in ("use", "family", "given") if k in n}
        for n in patient.get("name", [])
        if n.get("family") or n.get("given")
    ]
    if names:
        projection["name"] = names
    telecom = [
        {"system": t.get("system"), "value": t.get("value")}
        for t in patient.get("telecom", [])
    ]
    if telecom:
        projection["telecom"] = telecom
    for field in ("gender", "birthDate"):
        if field in patient:
            projection[field] = patient[field]
    addresses = [
        {
            k: a[k]
            for k in ("use", "line", "city", "district", "state", "postalCode", "country")
            if k in a
        }
        for a in patient.get("address", [])
    ]
    if addresses:
        projection["address"] = addresses
    return projection


def emedication_group_instances(pcr: PatientCareReport) -> list[dict]:
    """One NemsisEMedicationGroup logical instance per MedicationGroup, in
    document order (pairs 1:1 with the native mapper's MedicationAdministration
    output). Emits EITHER the valued eMedications_03 or its _pn — the maps
    dispatch on presence."""
    instances: list[dict] = []
    for group in pcr.groups("eMedications", "eMedications.MedicationGroup"):
        instance: dict = {"resourceType": "NemsisEMedicationGroup"}
        for element_id in ("eMedications.01", "eMedications.02", "eMedications.04",
                           "eMedications.05", "eMedications.06", "eMedications.10"):
            element = group.first(element_id)
            if element is not None and element.has_value:
                instance[element_id.replace(".", "_")] = element.value
        medication = group.first("eMedications.03")
        if medication is not None and medication.has_value:
            instance["eMedications_03"] = medication.value
        elif medication is not None and medication.pn:
            instance["eMedications_03_pn"] = medication.pn
        instances.append(instance)
    return instances


def medadmin_oracle_projection(resource: dict) -> dict:
    """The map-covered surface of a MedicationAdministration: status,
    effective, medication/statusReason codings, route SNOMED code, dose value.
    Native-only enrichments (dual-coded NEMSIS secondaries, performer refs,
    prior-care extension, dose unit displays) are excluded by construction."""
    projection: dict = {}
    for field in ("status", "effectiveDateTime"):
        if field in resource:
            projection[field] = resource[field]
    med = resource.get("medicationCodeableConcept", {})
    rx = [c["code"] for c in med.get("coding", [])
          if c.get("system") == "http://www.nlm.nih.gov/research/umls/rxnorm" and c.get("code")]
    if rx:
        projection["medication_rxnorm"] = rx
    reasons = resource.get("statusReason") or []
    if isinstance(reasons, dict):
        reasons = [reasons]
    pn = sorted(c["code"] for r in reasons for c in r.get("coding", [])
                if c.get("system", "").endswith("/NEMSIS") and c.get("code"))
    if pn:
        projection["status_reason_nemsis"] = pn
    dosage = resource.get("dosage") or {}
    # A coding with a system but no code = an unmatched ConceptMap translate
    # (e.g. nebulizer/IV-pump routes with no confident SNOMED target): both
    # engines agree there is no standard route, so treat it as absent.
    route = [c["code"] for c in dosage.get("route", {}).get("coding", [])
             if c.get("system") == "http://snomed.info/sct" and c.get("code")]
    if route:
        projection["route_snomed"] = route
    dose_value = dosage.get("dose", {}).get("value")
    if dose_value is not None:
        projection["dose_value"] = float(dose_value)
    return projection


def evitals_group_instances(pcr: PatientCareReport) -> list[dict]:
    """One NemsisEVitalsGroup logical instance (BP slice) per VitalGroup, in
    document order. Values and NV attributes are mutually exclusive per element
    (value XOR _nv), mirroring the nil mechanics."""
    instances: list[dict] = []
    for group in pcr.groups("eVitals", "eVitals.VitalGroup"):
        instance: dict = {"resourceType": "NemsisEVitalsGroup"}
        for element_id in ("eVitals.01", "eVitals.02", "eVitals.08"):
            element = group.first(element_id)
            if element is not None and element.has_value:
                instance[element_id.replace(".", "_")] = element.value
        for element_id in ("eVitals.06", "eVitals.07"):
            element = group.first(element_id)
            key = element_id.replace(".", "_")
            if element is not None and element.has_value:
                instance[key] = element.value
            elif element is not None and element.nv:
                instance[f"{key}_nv"] = element.nv
        instances.append(instance)
    return instances


def bp_oracle_projection(resource: dict) -> dict:
    """Map-covered surface of a BP panel Observation: status, the shared group
    timestamp, and per-component value-or-DAR. Components the native mapper
    synthesizes for elements ABSENT from the source group (its both-components
    profile fill: a DAR with no NEMSIS coding) are excluded — that fill is a
    US Core conformance enrichment outside the declarative map's scope."""
    projection: dict = {"status": resource.get("status")}
    if "effectiveDateTime" in resource:
        projection["effectiveDateTime"] = resource["effectiveDateTime"]
    loinc = [c["code"] for c in resource.get("code", {}).get("coding", [])
             if c.get("system") == "http://loinc.org"]
    projection["code_loinc"] = loinc
    components: dict = {}
    for comp in resource.get("component", []):
        codes = [c["code"] for c in comp.get("code", {}).get("coding", [])
                 if c.get("system") == "http://loinc.org"]
        if not codes:
            continue
        if "valueQuantity" in comp:
            components[codes[0]] = {"value": float(comp["valueQuantity"]["value"])}
        else:
            dar = comp.get("dataAbsentReason", {}).get("coding", [])
            # Source-backed NV components carry the NEMSIS secondary coding
            # (dual-coding, ADR-003 — both engines emit it). A DAR WITHOUT a
            # NEMSIS coding is the native mapper's both-components profile
            # fill for a source-absent element: out of the map's scope.
            if any(c.get("system", "").endswith("/NEMSIS") for c in dar):
                dar_code = next((c.get("code") for c in dar
                                 if c.get("system", "").endswith("data-absent-reason")), None)
                components[codes[0]] = {"dar": dar_code}
    projection["components"] = components
    return projection


def eprocedure_group_instances(pcr: PatientCareReport) -> list[dict]:
    """One NemsisEProcedureGroup logical instance per ProcedureGroup."""
    instances: list[dict] = []
    for group in pcr.groups("eProcedures", "eProcedures.ProcedureGroup"):
        instance: dict = {"resourceType": "NemsisEProcedureGroup"}
        for element_id in ("eProcedures.01", "eProcedures.02", "eProcedures.06"):
            element = group.first(element_id)
            if element is not None and element.has_value:
                instance[element_id.replace(".", "_")] = element.value
        code = group.first("eProcedures.03")
        if code is not None and code.has_value:
            instance["eProcedures_03"] = code.value
        elif code is not None and code.pn:
            instance["eProcedures_03_pn"] = code.pn
        instances.append(instance)
    return instances


def procedure_oracle_projection(resource: dict) -> dict:
    """Map-covered surface of a Procedure: status, performed, SNOMED code /
    NEMSIS statusReason, NEMSIS outcome coding."""
    projection: dict = {"status": resource.get("status")}
    if "performedDateTime" in resource:
        projection["performedDateTime"] = resource["performedDateTime"]
    snomed = [c["code"] for c in resource.get("code", {}).get("coding", [])
              if c.get("system") == "http://snomed.info/sct" and c.get("code")]
    if snomed:
        projection["code_snomed"] = snomed
    reason = resource.get("statusReason") or {}
    pn = sorted(c["code"] for c in reason.get("coding", [])
                if c.get("system", "").endswith("/NEMSIS") and c.get("code"))
    if pn:
        projection["status_reason_nemsis"] = pn
    outcome = [c["code"] for c in (resource.get("outcome") or {}).get("coding", [])
               if c.get("system", "").endswith("/NEMSIS") and c.get("code")]
    if outcome:
        projection["outcome_nemsis"] = outcome
    return projection


def esituation_instance(pcr: PatientCareReport) -> dict | None:
    """The eSituation impression slice, or None when no primary impression."""
    impression = pcr.first("eSituation.11")
    if impression is None or not impression.has_value:
        return None
    instance: dict = {"resourceType": "NemsisESituation", "eSituation_11": impression.value}
    onset = pcr.first("eSituation.01")
    if onset is not None and onset.has_value:
        instance["eSituation_01"] = onset.value
    return instance


def condition_oracle_projection(resource: dict) -> dict:
    """Map-covered surface of the primary-impression Condition."""
    projection: dict = {}
    icd = [c["code"] for c in resource.get("code", {}).get("coding", [])
           if c.get("system") == "http://hl7.org/fhir/sid/icd-10-cm" and c.get("code")]
    if icd:
        projection["code_icd10"] = icd
    if "onsetDateTime" in resource:
        projection["onsetDateTime"] = resource["onsetDateTime"]
    clinical = [c["code"] for c in (resource.get("clinicalStatus") or {}).get("coding", [])]
    if clinical:
        projection["clinical_status"] = clinical
    categories = sorted(
        c["code"]
        for cat in resource.get("category", [])
        for c in cat.get("coding", [])
        if c.get("system", "").endswith("condition-category")
    )
    if categories:
        projection["categories"] = categories
    return projection


def epatient_instance(pcr: PatientCareReport) -> dict:
    """The ePatient panel as a NemsisEPatient logical-model instance.

    Element ids become underscore names (ePatient.02 -> ePatient_02); only
    valued elements are exported (NV/PN handling is a native-helper concern
    the declarative maps do not cover — Architecture §9 practical note).
    """
    instance: dict = {"resourceType": "NemsisEPatient"}
    for element_id in _EPATIENT_SINGLE:
        element = pcr.first(element_id)
        if element is not None and element.has_value:
            instance[element_id.replace(".", "_")] = element.value
    for element_id in _EPATIENT_REPEATING:
        values = [e.value for e in pcr.all(element_id) if e.has_value]
        if values:
            instance[element_id.replace(".", "_")] = values
    return instance

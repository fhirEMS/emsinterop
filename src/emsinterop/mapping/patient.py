"""ePatient -> Patient (US Core / IHE PCC).

Sex: ePatient.25 is the source of truth; ePatient.13 Gender is deprecated in
3.5.0 and used only as legacy fallback (ADR-007). Race is dual-carried via the
US Core extensions (mPSC pcc-uv-* reconciliation happens at document assembly,
ADR-006). Identity is temporary — never fabricate an MRN (ADR-004).
"""

from __future__ import annotations

from ..issues import Disposition
from ..model import NemsisElement
from ..terminology import conceptmaps, nv_pn, registry, systems
from . import common
from .context import MappingContext

_RACE_ETHNICITY_CODES = {"2514007"}  # Hispanic or Latino -> us-core-ethnicity
_AGE_UNIT_TO_UCUM = {
    "2516001": ("d", "days"),
    "2516003": ("h", "hours"),
    "2516005": ("min", "minutes"),
    "2516007": ("mo", "months"),
    "2516009": ("a", "years"),
}


def _gender_element(ctx: MappingContext) -> NemsisElement | None:
    sex = ctx.pcr.first("ePatient.25")
    if sex is not None:
        return sex
    legacy = ctx.pcr.first("ePatient.13")
    if legacy is not None:
        ctx.log(
            "ePatient.13",
            Disposition.MAPPED,
            "ePatient.25 absent; used deprecated ePatient.13 as legacy fallback (ADR-007)",
            "information",
        )
    return legacy


def _apply_sex(ctx: MappingContext, patient: dict) -> None:
    el = _gender_element(ctx)
    if el is None:
        ctx.log("ePatient.25", Disposition.SEEDED,
                "no sex recorded (neither ePatient.25 nor the deprecated .13); "
                "Patient.gender absent and the US Core claim withheld",
                "information")
        return
    if el.has_value:
        genders = conceptmaps.translate(
            "cm-nemsis-sex", el.value, systems.ADMINISTRATIVE_GENDER
        )
        if genders:
            patient["gender"] = genders[0]["code"]
        birthsex = conceptmaps.translate("cm-nemsis-birthsex", el.value, systems.BIRTHSEX)
        if birthsex:
            patient.setdefault("extension", []).append(
                {"url": systems.US_CORE_BIRTHSEX_EXT, "valueCode": birthsex[0]["code"]}
            )
        if not genders:
            ctx.log("ePatient.25", Disposition.SEEDED,
                    f"sex code {el.value} has no administrative-gender target "
                    "(see cm-nemsis-sex); Patient.gender absent and the US Core "
                    "claim withheld", "information")
    elif el.nv or el.pn:
        # Absence maps to administrative-gender#unknown via cm-nemsis-sex.
        # Leaving gender absent fails us-core-patient's min=1 AND cascades to
        # every resource whose subject must reference a us-core-patient — the
        # whole document loses conformance over one unrecorded field.
        # `unknown` is FHIR's own "the gender is not known", which is the
        # receiver's situation however it came about. The precise NV/PN stays
        # in the ledger, and the map marks these rows `wider` so a reverse
        # mapping can never turn `unknown` back into "Refused".
        absent = conceptmaps.translate(
            "cm-nemsis-sex", el.nv or el.pn, systems.ADMINISTRATIVE_GENDER
        )
        if absent:
            patient["gender"] = absent[0]["code"]
        else:
            patient["_gender"] = common.primitive_absent_extension(el)
        ctx.log("ePatient.25", Disposition.SEEDED,
                f"sex not available ({'NV ' + el.nv if el.nv else 'PN ' + el.pn}); "
                "Patient.gender mapped to administrative-gender#unknown "
                "(cm-nemsis-sex, equivalence=wider — not reversible); the "
                "precise NEMSIS reason is retained here, not in the resource",
                "information")


def _apply_race(ctx: MappingContext, patient: dict) -> None:
    race_extension: dict = {"url": systems.US_CORE_RACE_EXT, "extension": []}
    texts: list[str] = []
    for el in ctx.pcr.all("ePatient.14"):
        if not el.has_value:
            continue
        display = registry.display("ePatient.14", el.value)
        if el.value in _RACE_ETHNICITY_CODES:
            cdc = conceptmaps.translate("cm-nemsis-race", el.value, systems.CDC_RACE_ETHNICITY)
            eth: dict = {"url": systems.US_CORE_ETHNICITY_EXT, "extension": []}
            if cdc:
                eth["extension"].append({"url": "ombCategory", "valueCoding": cdc[0]})
            eth["extension"].append({"url": "text", "valueString": display or el.value})
            patient.setdefault("extension", []).append(eth)
            continue
        cdc = conceptmaps.translate("cm-nemsis-race", el.value, systems.CDC_RACE_ETHNICITY)
        if cdc:
            race_extension["extension"].append({"url": "ombCategory", "valueCoding": cdc[0]})
        else:
            ctx.log(
                "ePatient.14",
                Disposition.SEEDED,
                f"race code {el.value} has no CDC Race&Ethnicity target (see cm-nemsis-race); "
                "carried as text only",
            )
        if display:
            texts.append(display)
    if texts or race_extension["extension"]:
        race_extension["extension"].append(
            {"url": "text", "valueString": ", ".join(texts) or "unknown"}
        )
        patient.setdefault("extension", []).append(race_extension)


def _apply_birth_and_age(ctx: MappingContext, patient: dict) -> None:
    # Read age/unit unconditionally: with a DOB they are covered (derivable);
    # without one they become an age Observation so the stated age isn't lost.
    age = ctx.pcr.first("ePatient.15")
    unit = ctx.pcr.first("ePatient.16")
    dob = ctx.pcr.first("ePatient.17")
    if dob is not None and dob.has_value:
        patient["birthDate"] = dob.value
        return
    if dob is not None and dob.nv:
        patient["_birthDate"] = common.primitive_absent_extension(dob)
    if age is not None and age.has_value:
        ucum, unit_name = (None, None)
        if unit is not None and unit.has_value:
            ucum, unit_name = _AGE_UNIT_TO_UCUM.get(unit.value, (None, None))
        obs = {
            "resourceType": "Observation",
            "id": ctx.rid("Observation", "ePatient.15"),
            "status": "final",
            "code": common.loinc("30525-0", "Age"),
            "subject": {"reference": f"Patient/{patient['id']}"},
        }
        if common.is_numeric(age.value):
            obs["valueQuantity"] = common.quantity(age.value, unit_name, ucum)
        else:
            obs["dataAbsentReason"] = common.unusable_value_concept("error")
        if ctx.encounter_id:
            obs["encounter"] = ctx.encounter_ref()
        ctx.add(obs)


def map_patient(ctx: MappingContext) -> dict:
    patient: dict = {
        "resourceType": "Patient",
        "id": ctx.rid("Patient"),
        "identifier": [],
    }

    # Identifiers: agency patient id + PCR-scoped temp id; never a fabricated MRN.
    pid = ctx.pcr.first("ePatient.01")
    if pid is not None and pid.has_value:
        ident = common.identifier(systems.PATIENT_AGENCY_ID, pid.value)
        ident["use"] = "usual"
        patient["identifier"].append(ident)
    temp = common.identifier(systems.PCR_ID, ctx.pcr_number or "unknown")
    temp["use"] = "temp"
    patient["identifier"].append(temp)
    ssn = ctx.pcr.first("ePatient.12")
    if ssn is not None and ssn.has_value:
        patient["identifier"].append(common.identifier(systems.US_SSN, ssn.value))

    family = ctx.pcr.first("ePatient.02")
    given = ctx.pcr.first("ePatient.03")
    middle = ctx.pcr.first("ePatient.04")
    name: dict = {"use": "official"}
    if family is not None and family.has_value:
        name["family"] = family.value
    if given is not None and given.has_value:
        name["given"] = [given.value]
        if middle is not None and middle.has_value:
            name["given"].append(middle.value)
    if len(name) > 1:
        patient["name"] = [name]
    elif family is not None and family.nv:
        # Unknown patient: keep the NV as a data-absent extension on name.
        patient["name"] = [{"extension": [nv_pn.data_absent_extension(family.nv)]}]

    address: dict = {}
    for element_id, key in [
        ("ePatient.05", "line"),
        ("ePatient.06", "city"),
        ("ePatient.07", "district"),
        ("ePatient.08", "state"),
        ("ePatient.09", "postalCode"),
        ("ePatient.10", "country"),
    ]:
        el = ctx.pcr.first(element_id)
        if el is not None and el.has_value:
            if key == "line":
                address["line"] = [el.value]
                continue
            # NEMSIS codes places; FHIR names them. The code never goes into a
            # name field — see common.address_field and the city-is-a-gnis-code
            # gap. The GNIS id is preserved as an extension so nothing is lost.
            if key == "city":
                extension = common.city_gnis_extension(el.value)
                if extension:
                    address.setdefault("extension", []).append(extension)
            translated = common.address_field(key, el.value, ctx.city_gazetteer)
            if translated:
                address[translated[0]] = translated[1]
    if address:
        address["use"] = "home"
        patient["address"] = [address]

    telecom = []
    for el in ctx.pcr.all("ePatient.18"):
        if el.has_value:
            telecom.append({"system": "phone", "value": el.value})
    for el in ctx.pcr.all("ePatient.19"):
        if el.has_value:
            telecom.append({"system": "email", "value": el.value})
    if telecom:
        patient["telecom"] = telecom

    _apply_sex(ctx, patient)
    _apply_race(ctx, patient)
    if common.can_claim_us_core_patient(patient):
        common.claim_profiles(patient, "us-core-patient")

    ctx.patient_id = patient["id"]
    ctx.add(patient)
    _apply_birth_and_age(ctx, patient)
    return patient

"""NV/PN engine + ConceptMap execution + dual-coding."""

from emsinterop.terminology import conceptmaps, nv_pn, registry, systems


def test_nv_to_data_absent_reason():
    assert nv_pn.data_absent_code("7701001") == "not-applicable"
    assert nv_pn.data_absent_code("7701003") == "unknown"
    assert nv_pn.data_absent_code("7701005") == "masked"


def test_section_empty_reason_from_nv():
    assert nv_pn.section_empty_reason("7701001")["coding"][0]["code"] == "nilknown"
    assert nv_pn.section_empty_reason("7701003")["coding"][0]["code"] == "notasked"
    assert nv_pn.section_empty_reason(None)["coding"][0]["code"] == "unavailable"


def test_pn_concept_carries_nemsis_code():
    concept = nv_pn.pn_concept("8801013")
    assert concept["coding"][0]["code"] == "8801013"
    assert concept["coding"][0]["system"] == systems.NEMSIS
    assert concept["text"] == "No Known Drug Allergy"


def test_registry_display():
    assert registry.display("ePatient.25", "9919001") == "Female"
    assert registry.element_name("eVitals.26") == "Level of Responsiveness (AVPU)"
    assert registry.is_known("eMedications.04", "9927023")


def test_conceptmap_translate_sex():
    genders = conceptmaps.translate("cm-nemsis-sex", "9919003", systems.ADMINISTRATIVE_GENDER)
    assert genders == [
        {"system": systems.ADMINISTRATIVE_GENDER, "code": "male", "display": "Male"}
    ]


def test_dual_code_keeps_nemsis_original():
    concept = conceptmaps.dual_code(
        "eMedications.04", "9927023", "cm-nemsis-medroute", systems.SNOMED
    )
    system_codes = [(c["system"], c["code"]) for c in concept["coding"]]
    assert (systems.SNOMED, "47625008") in system_codes
    assert (systems.NEMSIS, "9927023") in system_codes
    assert concept["text"] == "Intravenous (IV)"


def test_dual_code_unmatched_falls_back_to_nemsis_only():
    # MENA has no CDC target — the NEMSIS coding must survive alone.
    concept = conceptmaps.dual_code("ePatient.14", "2514013", "cm-nemsis-race")
    assert [c["system"] for c in concept["coding"]] == [systems.NEMSIS]
    assert concept["coding"][0]["code"] == "2514013"

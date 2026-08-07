"""Canonical system URIs used across the mapper."""

# Pass-through clinical terminologies already coded in NEMSIS source data.
SNOMED = "http://snomed.info/sct"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"

# NEMSIS code system. We own a clean local copy (ADR-003 #5); the canonical URL
# is the mPSC IG's so codings remain conformant with the IG when it stabilizes.
NEMSIS = "https://profiles.ihe.net/PCC/mPSC/CodeSystem/NEMSIS"

# FHIR core / US Core
DATA_ABSENT_REASON = "http://terminology.hl7.org/CodeSystem/data-absent-reason"
DATA_ABSENT_REASON_EXT = "http://hl7.org/fhir/StructureDefinition/data-absent-reason"
OBSERVATION_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"
CONDITION_CATEGORY = "http://terminology.hl7.org/CodeSystem/condition-category"
CONDITION_CLINICAL = "http://terminology.hl7.org/CodeSystem/condition-clinical"
CONDITION_VER_STATUS = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
ALLERGY_CLINICAL = "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical"
ALLERGY_VERIFICATION = "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification"
V3_ACT_CODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
V3_ACT_PRIORITY = "http://terminology.hl7.org/CodeSystem/v3-ActPriority"
V3_ROLE_CODE = "http://terminology.hl7.org/CodeSystem/v3-RoleCode"
CDC_RACE_ETHNICITY = "urn:oid:2.16.840.1.113883.6.238"
US_CORE_RACE_EXT = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race"
US_CORE_ETHNICITY_EXT = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity"
US_CORE_BIRTHSEX_EXT = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-birthsex"
ADMINISTRATIVE_GENDER = "http://hl7.org/fhir/administrative-gender"
BIRTHSEX = "http://terminology.hl7.org/CodeSystem/v3-AdministrativeGender"
US_NPI = "http://hl7.org/fhir/sid/us-npi"
US_SSN = "http://hl7.org/fhir/sid/us-ssn"

# Identifier system URIs for NEMSIS business identifiers (project-owned URNs).
PCR_ID = "urn:nemsis:identifier:pcr"
INCIDENT_ID = "urn:nemsis:identifier:incident"
RESPONSE_ID = "urn:nemsis:identifier:response"
AGENCY_STATE_ID = "urn:nemsis:identifier:agency-state-id"
AGENCY_NUMBER = "urn:nemsis:identifier:agency-number"
PATIENT_AGENCY_ID = "urn:nemsis:identifier:patient"
PERSONNEL_ID = "urn:nemsis:identifier:personnel"

# Security labels (mapper tags, fhirEngine enforces — hard rule).
V3_CONFIDENTIALITY = "http://terminology.hl7.org/CodeSystem/v3-Confidentiality"
V3_ACT_CODE_42CFR = "42CFRPart2"

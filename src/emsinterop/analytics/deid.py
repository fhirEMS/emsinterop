"""DuckDB de-identified (Safe Harbor) projection over fhirEngine Gold.

Architecture §7 / ADR-010: the identified operational store (fhirEngine) and
the analytic store stay cleanly separated. This module reads fhirEngine's
Delta tables (gold/<type>, falling back to bronze/<type> in `single`-mode
deployments) READ-ONLY, and materializes flattened, de-identified analytic
rows as separate Delta tables. These are NOT FHIR resources — ADR-009's
"fhirEngine is the only writer of FHIR tables" is untouched; §7 explicitly
sanctions this projection as the mapper-side analytics path.

De-identification is by CONSTRUCTION, not redaction: rows are built from an
allowlist of fields, so a new upstream field can never leak — it simply is
not projected. HIPAA Safe Harbor specifics applied:
  - resource ids replaced by salted-hash pseudonyms (linkage within one
    projection run by default; pass a stable salt for cross-run linkage),
  - all dates reduced to year,
  - ages capped at 90 ("90 or over" aggregation),
  - geography no finer than state + ZIP3, with the 17 restricted
    low-population ZIP3 prefixes nulled,
  - names, addresses, telecoms, birth dates, and business identifiers are
    never selected.

Requires the optional `analytics` extra (duckdb + deltalake + pyarrow).
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from ..log import event, get_logger

logger = get_logger("deid")

# ZIP3 prefixes with <20k population per the Safe Harbor guidance — must not
# be released even truncated.
RESTRICTED_ZIP3 = {
    "036", "059", "063", "102", "203", "556", "692", "790", "821", "823",
    "830", "831", "878", "879", "884", "890", "893",
}

_US_CORE_RACE = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race"
_US_CORE_ETHNICITY = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity"
_NEMSIS = "https://profiles.ihe.net/PCC/mPSC/CodeSystem/NEMSIS"
_LOINC = "http://loinc.org"


def zip3(postal_code: str | None) -> str | None:
    if not postal_code or len(postal_code) < 3:
        return None
    prefix = postal_code[:3]
    return None if prefix in RESTRICTED_ZIP3 else prefix


def year_of(iso_datetime: str | None) -> int | None:
    if not iso_datetime or len(iso_datetime) < 4:
        return None
    try:
        return int(iso_datetime[:4])
    except ValueError:
        return None


def capped_age(birth_date: str | None, reference: str | None) -> int | None:
    """Age in whole years at the reference date, capped at 90 (Safe Harbor
    aggregates everyone 90 and over)."""
    birth_year, ref_year = year_of(birth_date), year_of(reference)
    if birth_year is None or ref_year is None:
        return None
    return min(max(ref_year - birth_year, 0), 90)


def _pseudonym(salt: str, resource_id: str | None) -> str | None:
    if not resource_id:
        return None
    return hashlib.sha256(f"{salt}|{resource_id}".encode()).hexdigest()[:16]


def _coding_code(concept: dict | None, system: str | None = None) -> str | None:
    for coding in (concept or {}).get("coding", []):
        if system is None or coding.get("system") == system:
            return coding.get("code")
    return None


def _omb_category(patient: dict, extension_url: str) -> str | None:
    for ext in patient.get("extension", []):
        if ext.get("url") == extension_url:
            for nested in ext.get("extension", []):
                if nested.get("url") == "ombCategory":
                    return (nested.get("valueCoding") or {}).get("code")
    return None


def _current_bodies(delta_base: str | Path, resource_type: str) -> list[dict]:
    """Current, non-deleted resource bodies from gold/<type>, else
    bronze/<type> (single-mode: Bronze IS the serving tier). DuckDB does the
    current-version selection; bodies come back as parsed JSON."""
    try:
        import duckdb
        from deltalake import DeltaTable
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(
            "the de-id projection requires the 'analytics' extra: "
            "pip install emsinterop[analytics]"
        ) from error

    base = Path(delta_base)
    for tier in ("gold", "bronze"):
        table_dir = base / tier / resource_type.lower()
        if not table_dir.is_dir():
            continue
        arrow = DeltaTable(str(table_dir)).to_pyarrow_table()
        connection = duckdb.connect()
        connection.register("t", arrow)
        current = ("coalesce(is_current, true)" if "is_current" in arrow.column_names
                   else "true")
        rows = connection.execute(
            f"""
            SELECT body_json FROM t
            WHERE {current} AND NOT coalesce(deleted, false)
            QUALIFY row_number() OVER (PARTITION BY id ORDER BY version_id DESC) = 1
            """
        ).fetchall()
        connection.close()
        return [json.loads(row[0]) for row in rows if row[0]]
    return []


def project(
    delta_base: str | Path,
    out_dir: str | Path,
    salt: str | None = None,
) -> dict:
    """Materialize the Safe Harbor projection: <out_dir>/encounters and
    <out_dir>/vitals Delta tables (mode=overwrite — the projection is a
    reproducible derived artifact, re-run it whenever Gold moves)."""
    import pyarrow as pa
    from deltalake import write_deltalake

    salt = salt or secrets.token_hex(16)
    patients = {p["id"]: p for p in _current_bodies(delta_base, "patient")}
    encounters = _current_bodies(delta_base, "encounter")
    observations = _current_bodies(delta_base, "observation")

    def patient_of(reference: dict | None) -> dict:
        ref = (reference or {}).get("reference", "")
        return patients.get(ref.removeprefix("Patient/"), {})

    encounter_rows = []
    for enc in encounters:
        patient = patient_of(enc.get("subject"))
        start = (enc.get("period") or {}).get("start")
        address = (patient.get("address") or [{}])[0]
        encounter_rows.append({
            "encounter_pseudo_id": _pseudonym(salt, enc.get("id")),
            "patient_pseudo_id": _pseudonym(salt, patient.get("id")),
            "year": year_of(start),
            "age": capped_age(patient.get("birthDate"), start),
            "gender": patient.get("gender"),
            "race_omb": _omb_category(patient, _US_CORE_RACE),
            "ethnicity_omb": _omb_category(patient, _US_CORE_ETHNICITY),
            "state": address.get("state"),
            "zip3": zip3(address.get("postalCode")),
            "status": enc.get("status"),
            "class_code": (enc.get("class") or {}).get("code"),
            "priority_nemsis": _coding_code(enc.get("priority"), _NEMSIS),
            "disposition_nemsis": _coding_code(
                (enc.get("hospitalization") or {}).get("dischargeDisposition"),
                _NEMSIS),
        })

    vital_rows = []
    for obs in observations:
        categories = {
            coding.get("code")
            for concept in obs.get("category", [])
            for coding in concept.get("coding", [])
        }
        if "vital-signs" not in categories:
            continue
        pseudo = {
            "encounter_pseudo_id": _pseudonym(
                salt, (obs.get("encounter") or {}).get("reference", "")
                .removeprefix("Encounter/") or None),
            "patient_pseudo_id": _pseudonym(
                salt, (obs.get("subject") or {}).get("reference", "")
                .removeprefix("Patient/") or None),
            "year": year_of(obs.get("effectiveDateTime")),
        }
        candidates = [(_coding_code(obs.get("code"), _LOINC)
                       or _coding_code(obs.get("code")), obs)]
        candidates += [
            (_coding_code(comp.get("code"), _LOINC)
             or _coding_code(comp.get("code")), comp)
            for comp in obs.get("component", [])
        ]
        for code, carrier in candidates:
            quantity = carrier.get("valueQuantity")
            if code is None or quantity is None:
                continue
            vital_rows.append({
                **pseudo,
                "code": code,
                "value": quantity.get("value"),
                "unit": quantity.get("unit") or quantity.get("code"),
            })

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    schemas = {
        "encounters": (encounter_rows, pa.schema([
            ("encounter_pseudo_id", pa.string()), ("patient_pseudo_id", pa.string()),
            ("year", pa.int32()), ("age", pa.int32()), ("gender", pa.string()),
            ("race_omb", pa.string()), ("ethnicity_omb", pa.string()),
            ("state", pa.string()), ("zip3", pa.string()), ("status", pa.string()),
            ("class_code", pa.string()), ("priority_nemsis", pa.string()),
            ("disposition_nemsis", pa.string()),
        ])),
        "vitals": (vital_rows, pa.schema([
            ("encounter_pseudo_id", pa.string()), ("patient_pseudo_id", pa.string()),
            ("year", pa.int32()), ("code", pa.string()),
            ("value", pa.float64()), ("unit", pa.string()),
        ])),
    }
    for name, (rows, schema) in schemas.items():
        write_deltalake(str(out / name), pa.Table.from_pylist(rows, schema=schema),
                        mode="overwrite")

    event(logger, "deid.projected", rows=len(encounter_rows) + len(vital_rows),
          path=out)
    return {"encounters": len(encounter_rows), "vitals": len(vital_rows),
            "path": str(out)}

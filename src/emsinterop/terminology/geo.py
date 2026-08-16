"""NEMSIS geographic codes -> what FHIR and CDA actually ask for.

NEMSIS stores places as codes: a state is the two-digit ANSI/FIPS code (`49`),
a city is a GNIS feature id (`1454997`). FHIR asks for something else entirely
— `Address.city` is "Name of city, town etc." and `Address.state` is
"Sub-unit of country (abbreviations ok)" — and so does CDA.

Writing the code into the name field is not a formatting quirk. A receiving
system displays it verbatim, so a clinician reads "1454997, 49" as the
patient's address. It validates everywhere, because both fields are `string`.

**States resolve here.** The FIPS state table is closed, stable and public, so
it is embedded and complete; a state code either resolves or it is not a state.

**Cities do not.** GNIS is a gazetteer of millions of entries that this project
has no business embedding, so `Address.city` is populated only when a caller
supplies a resolver — the same posture as agency and personnel names. What is
never done is passing the code off as the name.
"""

from __future__ import annotations

#: ANSI/FIPS state code -> USPS abbreviation. Closed set: 50 states, DC, and
#: the inhabited territories NEMSIS records.
FIPS_TO_USPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
    "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
}


def state_abbreviation(code: str | None) -> str | None:
    """USPS abbreviation for an ANSI/FIPS state code, or None if unknown.

    None rather than the code itself: returning `49` would put a number back in
    a field that means an abbreviation, which is the defect this exists to fix.
    """
    if not code:
        return None
    return FIPS_TO_USPS.get(str(code).strip().zfill(2))


def city_name(gnis: str | None, gazetteer: dict[str, str] | None = None) -> str | None:
    """City name for a GNIS feature id, if the caller supplied a gazetteer.

    GNIS has millions of entries and this project ships none of them, so the
    honest answer without a gazetteer is "unknown" — never the code.
    """
    if not gnis or not gazetteer:
        return None
    return gazetteer.get(str(gnis).strip())


#: The reverse map, for FHIR -> NEMSIS. FIPS <-> USPS is a bijection, so a
#: state survives a round trip intact.
USPS_TO_FIPS = {v: k for k, v in FIPS_TO_USPS.items()}


def state_code(abbreviation: str | None) -> str | None:
    """ANSI/FIPS code for a USPS abbreviation, or None if unknown."""
    if not abbreviation:
        return None
    return USPS_TO_FIPS.get(str(abbreviation).strip().upper())

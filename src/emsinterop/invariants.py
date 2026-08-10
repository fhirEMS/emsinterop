"""What must be true of *any* conversion, in one place.

These started as assertions inside `tests/test_hostile_corpus.py`, where they
could only ever be applied to the fixtures someone had thought to write. The
fuzz harness needs the same checks over tens of thousands of generated
documents, and a second copy of them would drift from the first — so the rules
live here and both callers share them.

Each rule has a **stable id**. The fuzz harness deduplicates findings by that
id, and a baseline of accepted findings is keyed on it, so renaming one is a
breaking change to the sweep's history rather than a cosmetic edit.

A violation is always a defect in the mapper, never in the input: every rule
here is about the FHIR that came out, and the input is XSD-valid by
construction. That is what makes the sweep's output actionable — there is no
"bad input" bucket to explain a finding away with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from .issues import Disposition
from .mapping import common
from .terminology import registry


@dataclass(frozen=True)
class Violation:
    """One broken rule. `rule` is stable; `detail` is free text for humans."""

    rule: str
    detail: str
    resource_id: str | None = None

    def signature(self) -> str:
        """What the fuzz harness deduplicates on.

        Deliberately excludes `detail` — it carries resource ids and values
        that differ per document, and including them would turn one defect into
        ten thousand distinct findings."""
        return self.rule


def _vital_signs(resource: dict) -> bool:
    return any(
        coding.get("code") == "vital-signs"
        for concept in resource.get("category", [])
        for coding in concept.get("coding", [])
    )


def check_nothing_dropped(result) -> list[Violation]:
    """The project's #1 hard rule: every source element is mapped or ledgered.

    A third path — present in the source, consumed by nobody, ledgered by
    nobody — is how a NEMSIS element disappears silently, which is the failure
    this whole project exists to prevent."""
    present = result.context.pcr.element_ids()
    flagged = {issue.element_id for issue in result.issues.issues}
    orphaned = present - result.context.consumed - flagged
    return [
        Violation("element-dropped-silently",
                  f"{element} present in source, neither consumed nor ledgered")
        for element in sorted(orphaned)
    ]


def check_no_unmapped_national(result) -> list[Violation]:
    """State and local elements may be deferred; the national dataset is what
    this project claims to cover, so a gap there is a finding."""
    return [
        Violation("national-element-unmapped", issue.element_id)
        for issue in result.issues.by_disposition(Disposition.UNMAPPED)
        if registry.is_national(issue.element_id)
    ]


def check_json_serializable(result) -> list[Violation]:
    """NaN and Infinity are valid Python floats and INVALID JSON. One leak
    anywhere in the graph makes the entire bundle unparseable by any conforming
    server, so this is checked at the wire boundary rather than per-field."""
    out = []
    for name, payload in (("transaction", result.transaction),
                          ("document", result.document)):
        try:
            json.dumps(payload, allow_nan=False)
        except ValueError as exc:
            out.append(Violation("json-not-serializable", f"{name}: {exc}"))
    return out


def check_request_urls(result) -> list[Violation]:
    """A PCR number is xs:string with no pattern, so it can carry / & ? #.
    Those must not leak into the URL's structure: an unescaped `?` truncates
    the search and could match the WRONG patient's resource."""
    out = []
    for entry in result.transaction.get("entry", []):
        url = entry.get("request", {}).get("url", "")
        # Asserted on the RAW url. parse_qs percent-DECODES, so a correctly
        # escaped value legitimately contains '?' once decoded, and checking
        # there would test nothing at all.
        if "#" in url or urlsplit(url).fragment:
            out.append(Violation("url-unescaped-fragment", url))
        if url.count("?") > 1:
            out.append(Violation("url-unescaped-query", url))
    return out


def check_vital_signs_conformance(result) -> list[Violation]:
    """vs-1: a vital-signs Observation must not carry a value-less
    `_effectiveDateTime`. The validator applies the base vitalsigns profile on
    the strength of `category`, NOT `meta.profile`, so the element has to be
    omitted entirely rather than merely stripped of its claim."""
    out = []
    for resource in result.resources:
        if resource.get("resourceType") != "Observation" or not _vital_signs(resource):
            continue
        if "_effectiveDateTime" in resource and "effectiveDateTime" not in resource:
            out.append(Violation("vs-1-valueless-effective",
                                 "value-less effective time on a vital sign",
                                 resource.get("id")))
    return out


def check_profile_claims_are_earned(result) -> list[Violation]:
    """A profile is claimed only when it can actually be met. Claiming one the
    resource cannot satisfy is worse than not claiming it: it invites a server
    to validate against a contract we knowingly break."""
    out = []
    for resource in result.resources:
        claims = resource.get("meta", {}).get("profile", [])
        kind = resource.get("resourceType")
        if kind == "Observation" and any(
                "vital-signs" in c or "blood-pressure" in c for c in claims):
            if not common.can_claim_vital_signs(resource):
                out.append(Violation("profile-claim-unearned",
                                     "us-core vital-signs claimed but not satisfiable",
                                     resource.get("id")))
        if kind == "Patient" and any("us-core-patient" in c for c in claims):
            # us-core-patient requires gender (min 1); a data-absent extension
            # does NOT satisfy it, and we never invent a value to pass.
            if not isinstance(resource.get("gender"), str):
                out.append(Violation("profile-claim-unearned",
                                     "us-core-patient claimed without a gender value",
                                     resource.get("id")))
    return out


def check_references_resolve(result) -> list[Violation]:
    """Every local reference must point at a resource in the same bundle.

    A dangling reference is not caught by JSON validity or by profile checks,
    and it survives all the way to a server, where it becomes a broken graph
    rather than a rejected transaction."""
    known = {f"{r['resourceType']}/{r['id']}" for r in result.resources}
    out = []

    def walk(node, owner):
        if isinstance(node, dict):
            target = node.get("reference")
            # Absolute and urn: references are resolved elsewhere (or by the
            # server); only relative Type/id references are ours to close.
            if (isinstance(target, str) and "/" in target
                    and not target.startswith(("http", "urn:", "#"))
                    and target not in known):
                out.append(Violation("reference-unresolved", target, owner))
            for value in node.values():
                walk(value, owner)
        elif isinstance(node, list):
            for value in node:
                walk(value, owner)

    for resource in result.resources:
        walk(resource, resource.get("id"))
    return out


#: Every rule, in the order a human would want to read failures.
RULES = (
    check_nothing_dropped,
    check_no_unmapped_national,
    check_json_serializable,
    check_request_urls,
    check_vital_signs_conformance,
    check_profile_claims_are_earned,
    check_references_resolve,
)


def check(result) -> list[Violation]:
    """Apply every rule to one conversion result."""
    out: list[Violation] = []
    for rule in RULES:
        out.extend(rule(result))
    return out

"""The gap-occupancy policy, enforced.

Where IHE is silent this project decides, and those decisions are legitimate.
What is not legitimate is letting them blur into conformance — a consumer
validating against the IG has to be able to tell which parts of our output the
standard actually specifies.

Two failures are easy to commit and invisible afterwards, so both are tested:

  1. **Canonical squatting.** Publishing a conformance resource whose `url` is
     someone else's canonical asserts we define that identifier. Two conflicting
     definitions of one URL break whichever terminology server loads ours
     second. Referencing a foreign canonical in `coding.system` is the opposite
     — it is what keeps our data conformant — so the tests distinguish them.

  2. **Undeclared local decisions.** An artifact minted with no registered gap
     is a fork nobody wrote down, and the person who finds it is an integrator
     wondering why our output has a field the IG never mentions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from emsinterop import conformance
from emsinterop.convert import convert
from emsinterop.terminology import systems

REPO = Path(__file__).resolve().parents[1]
MAPS = REPO / "maps"


def published_resources():
    """Every conformance resource this repo authors."""
    for path in sorted(MAPS.rglob("*.json")):
        data = json.loads(path.read_text())
        if isinstance(data, dict) and "url" in data:
            yield path, data


def test_we_publish_nothing_at_a_foreign_canonical():
    """The rule that matters most. `coding.system` may point anywhere; a
    published `url` may not."""
    squatted = [
        (path.name, data["url"])
        for path, data in published_resources()
        if conformance.is_foreign(data["url"])
    ]
    assert squatted == [], (
        "these resources claim to DEFINE a canonical owned by HL7/IHE/SNOMED; "
        f"reference it in coding.system instead: {squatted}"
    )


def test_every_authored_canonical_sits_under_our_base():
    stray = [
        (path.name, data["url"])
        for path, data in published_resources()
        if not conformance.is_ours(data["url"])
    ]
    assert stray == [], f"canonicals outside {conformance.CANONICAL_BASE}: {stray}"


def test_the_packaged_codesystem_does_not_claim_the_ihe_canonical():
    """We ship 2,321 concepts where the mPSC build has 18 TODO placeholders.
    That is a stand-in, published under our own identifier, and it records what
    it mirrors — not a redefinition of theirs."""
    from emsinterop.terminology.igpackage import nemsis_codesystem

    cs = nemsis_codesystem("0.0.0-test")
    assert conformance.is_ours(cs["url"])
    assert cs["url"] != systems.NEMSIS
    mirrored = [i["value"] for i in cs.get("identifier", [])]
    assert systems.NEMSIS in mirrored, (
        "the package must record which canonical it stands in for, or a "
        "consumer cannot tell what it is")


def test_codings_still_reference_the_ihe_canonical():
    """The other half: our DATA must keep pointing at the IG's canonical, so it
    becomes conformant the day the IG is fixed, with no migration."""
    assert systems.NEMSIS.startswith("https://profiles.ihe.net/")
    result = convert(REPO / "tests" / "fixtures" / "pcr_chest_pain.xml")[0]
    referenced = {
        coding.get("system")
        for resource in result.resources
        for coding in _codings(resource)
    }
    assert systems.NEMSIS in referenced, "NEMSIS codings stopped referencing mPSC"


def _codings(node):
    if isinstance(node, dict):
        if "system" in node and "code" in node:
            yield node
        for value in node.values():
            yield from _codings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _codings(value)


def test_every_artifact_we_mint_is_declared_in_the_gap_register():
    """An artifact with no registered gap is an undeclared fork."""
    registered = conformance.registered_artifacts()
    # ValueSets are generated systematically, one per NEMSIS element, and are
    # covered by the mapping-table gap rather than listed individually.
    undeclared = [
        data["url"] for _, data in published_resources()
        if data["url"] not in registered
        and "/ValueSet/" not in data["url"]
        and "/StructureMap/" not in data["url"]
        and "/ConceptMap/" not in data["url"]
    ]
    assert undeclared == [], (
        f"minted with no entry in conformance.GAPS: {undeclared}")


@pytest.mark.parametrize("gap", conformance.GAPS, ids=lambda g: g.id)
def test_every_gap_is_evidenced_and_has_an_exit(gap):
    """A gap report with no date is a rumour about a moving CI build, and a
    local decision with no retirement trigger is a permanent fork wearing a
    temporary label."""
    assert gap.finding and gap.decision
    assert gap.source.startswith("http"), "cite where this was verified"
    assert len(gap.verified) == 10 and gap.verified[4] == "-", (
        "verified must be an ISO date — these are CI builds and they move")
    assert gap.retirement, (
        f"{gap.id} has no retirement trigger: what would make this go away?")


def test_naming_systems_are_unchanged():
    """These name a scheme, not a document, so they are URNs on purpose.

    `resource-id` is load-bearing for identity — it appears in every
    conditional-update URL, so changing it would fail to match resources
    already stored in a fhirEngine and silently duplicate them. This test is
    here to make that a deliberate, visible act rather than a rename."""
    from emsinterop.mapping.context import RESOURCE_ID_SYSTEM
    from emsinterop.submit.bundle import RESOURCE_ID_SYSTEM as BUNDLE_SYSTEM

    assert RESOURCE_ID_SYSTEM == "urn:emsinterop:resource-id"
    assert BUNDLE_SYSTEM == RESOURCE_ID_SYSTEM, "identity system diverged"
    assert conformance.NAMING_SYSTEMS["resource-id"] == RESOURCE_ID_SYSTEM


def test_emitted_extensions_are_ours_and_resolvable():
    """Anything we invent that reaches a consumer must be dereferenceable, so
    they can find out what it means."""
    urls = set()

    def walk(node):
        if isinstance(node, dict):
            for extension in node.get("extension", []) + node.get("modifierExtension", []):
                urls.add(extension.get("url"))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    # Swept over the whole corpus: our one local extension is conditional
    # (eVitals.02 "obtained prior to this unit's care"), so a single fixture is
    # not evidence either way.
    fixtures = sorted((REPO / "tests" / "fixtures").glob("*.xml"))
    fixtures += sorted((REPO / "tests" / "fixtures" / "hostile").glob("*.xml"))
    for path in fixtures:
        for result in convert(path):
            walk(result.transaction)

    # Nested sub-extensions are named relatively by design (US Core race
    # carries `ombCategory`, `text`), and are scoped by their parent's URL.
    # Only absolute URIs are canonicals in their own right.
    local = {
        u for u in urls
        if u and "/" in u and not conformance.is_foreign(u)
    }
    assert local, "no local extension anywhere in the corpus to check"
    for url in local:
        assert conformance.is_ours(url), f"unresolvable local extension: {url}"


def test_summary_is_serialisable_and_complete():
    """It ships in the terminology package, so it must survive JSON and name
    every gap."""
    payload = json.loads(json.dumps(conformance.summary(), allow_nan=False))
    assert payload["canonicalBase"] == conformance.CANONICAL_BASE
    assert {g["id"] for g in payload["gaps"]} == {g.id for g in conformance.GAPS}

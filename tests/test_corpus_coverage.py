"""How much of the national dataset the generated corpus actually populates.

A clean sweep is only as meaningful as the surface it covers. When the corpus
sweep first reported 0 findings across 20,000 cases, that read as strong
evidence — until it was measured: only **19 of 83 national elements (22%)** ever
carried a real value. The other 64 were emitted as nil+NV, so the mapper's
handling of them was never executed at all. The volume was real; the coverage
was not.

This test exists so that can never quietly happen again. It is the honest
denominator for every "0 findings" claim the sweep makes.

The measurement lives here rather than in nemsynth because the list of national
elements comes from *this* repo's registry, and the generator must not depend
on its consumer — that inversion is what keeps it able to generate shapes we
did not think of.
"""

from __future__ import annotations

import pytest
from lxml import etree

from emsinterop.terminology import registry

NEMSIS_NS = "http://www.nemsis.org"
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"

#: Elements a *field* PCR legitimately leaves empty, with the reason. Anything
#: outside this set that stops being populated is a coverage regression, not a
#: design decision — which is the distinction this list exists to force.
OUT_OF_SCOPE = {
    # Written by the inbound outcome loop (ADT / discharge summary), never by
    # the crew at the time of the call. A field PCR carrying them would be
    # fiction.
    "eOutcome.01", "eOutcome.02",
    # Optional free "additional descriptors" with no clinical driver in any
    # scenario; populating them would be noise, not coverage.
    "eDisposition.18", "eDisposition.22", "eResponse.24",
}

#: Floor, not a target. Set below the measured 93% so ordinary scenario churn
#: does not fail the suite, but high enough that losing a whole section does.
MINIMUM_COVERAGE = 0.85


def _valued_elements(documents):
    """Every national element carrying a REAL value — not nil, not NV/PN."""
    national = {e for e in registry.elements() if registry.is_national(e)}
    valued = set()
    for document in documents:
        for element in etree.fromstring(document).iter():
            tag = etree.QName(element).localname
            if tag not in national or element.get(XSI_NIL) in ("true", "1"):
                continue
            if (element.text or "").strip():
                valued.add(tag)
    return national, valued


@pytest.fixture(scope="module")
def corpus():
    pytest.importorskip("nemsynth", reason="generator is an optional dev dep")
    from nemsynth.generate import generate_mci, generate_one, scenario_for

    documents = [generate_one(seed, scenario_for(seed, "mixed"), profile="medium")
                 for seed in range(60)]
    # MCI carries elements no single-patient record does (scene triage class,
    # multiple patients at scene), so it is part of the denominator.
    documents += [generate_mci(seed, 4, profile="medium") for seed in range(4)]
    return documents


def test_corpus_populates_most_of_the_national_dataset(corpus):
    national, valued = _valued_elements(corpus)
    coverage = len(valued) / len(national)
    missing = sorted(national - valued - OUT_OF_SCOPE)
    assert coverage >= MINIMUM_COVERAGE, (
        f"generated corpus populates only {coverage:.0%} of national elements "
        f"({len(valued)}/{len(national)}); a clean sweep over this corpus would "
        f"be weak evidence. Never valued: {missing}"
    )


def test_nothing_silently_leaves_the_covered_set(corpus):
    """Every unpopulated element must be a documented decision.

    Without this, a scenario edit that quietly stops populating a section would
    still pass the percentage floor by riding on the others."""
    _, valued = _valued_elements(corpus)
    undocumented = sorted(
        e for e in {x for x in registry.elements() if registry.is_national(x)}
        if e not in valued and e not in OUT_OF_SCOPE
    )
    assert undocumented == [], (
        "national elements are unpopulated and undocumented — either generate "
        f"them or add them to OUT_OF_SCOPE with a reason: {undocumented}"
    )


def test_out_of_scope_entries_are_real_elements():
    """A typo in OUT_OF_SCOPE would silently widen the exemption."""
    known = set(registry.elements())
    assert not (OUT_OF_SCOPE - known), f"unknown ids: {OUT_OF_SCOPE - known}"

"""The corpus-sweep harness.

Its value is entirely in the triage: a defect in a shared code path fires on
every document that reaches it, so without deduplication a sweep of 20,000
cases reports 20,000 findings and gets ignored. These tests pin the three
properties that make the output usable — findings collapse, they carry a
replayable reproduction, and the baseline distinguishes new from known.

`nemsynth` is not required here. It is a separate public repo and an optional
dev dependency, so the harness's own logic is tested against synthetic results
and only the end-to-end test is skipped when it is absent.
"""

from __future__ import annotations

import json

import pytest

from emsinterop import fuzz


def test_plan_rotates_every_axis():
    """A small sweep must still cover every combination, and case #137 must be
    the same case on every machine — otherwise a finding is not replayable."""
    cases = fuzz.plan(count=40, scenarios=["a", "b"], profiles=["clean", "high"],
                      versions=["3.5.0", "3.5.1"], mci=5, seed_start=1)
    assert len(cases) == 40
    assert {c["scenario"] for c in cases} == {"a", "b"}
    assert {c["profile"] for c in cases} == {"clean", "high"}
    assert {c["version"] for c in cases} == {"3.5.0", "3.5.1"}
    assert sum(1 for c in cases if c["mci"]) == 4      # every tenth
    assert cases == fuzz.plan(40, ["a", "b"], ["clean", "high"],
                              ["3.5.0", "3.5.1"], 5, 1)


def test_mci_can_be_disabled():
    cases = fuzz.plan(20, ["a"], ["clean"], ["3.5.0"], mci=0, seed_start=1)
    assert not any(c["mci"] for c in cases)


def test_findings_deduplicate_but_keep_a_few_examples():
    """One defect, ten thousand documents, one finding — with enough examples
    to see a pattern and not so many that the report becomes a dump."""
    finding = fuzz.Finding("crash:ValueError:vitals.py:88", "crash", "boom")
    for seed in range(10_000):
        finding.observe({"seed": seed, "scenario": "chest-pain",
                         "profile": "high", "version": "3.5.0", "mci": 0})
    assert finding.count == 10_000
    assert len(finding.examples) == 3


def test_reproduction_line_is_runnable():
    """A finding you cannot replay is a rumour. nemsynth is byte-reproducible
    for a given seed, so the seed plus the axes is a complete recipe."""
    finding = fuzz.Finding("x", "crash", "boom")
    finding.observe({"seed": 42, "scenario": "overdose", "profile": "high",
                     "version": "3.5.1", "mci": 0})
    line = finding.reproduce()
    assert "--seed 42" in line and "--scenario overdose" in line
    assert "--messiness high" in line and "--version 3.5.1" in line

    mci = fuzz.Finding("y", "crash", "boom")
    mci.observe({"seed": 7, "scenario": "mixed", "profile": "low",
                 "version": "3.5.0", "mci": 5})
    assert "--mci 5" in mci.reproduce()


def test_crash_signature_names_our_code_not_the_message():
    """Messages interpolate per-document values; keying on them would turn one
    defect into thousands of findings, which is the failure this prevents."""
    def inner(value):
        raise ValueError(f"could not convert {value!r}")

    signatures = set()
    for value in ("P", "p", "High"):
        try:
            inner(value)
        except ValueError as exc:
            signatures.add(fuzz._crash_signature(exc))
    assert len(signatures) == 1, "the same line produced different signatures"
    assert signatures.pop().startswith("crash:ValueError:")


def test_crash_signature_survives_a_frameless_traceback():
    """Robustness: the harness must never crash while reporting a crash."""
    assert fuzz._crash_signature(ValueError("no traceback")).endswith(":?")


def test_baseline_separates_new_from_known(tmp_path, capsys):
    """The property that lets this run unattended without crying wolf."""
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"accepted": ["known-rule"]}))
    assert fuzz.load_baseline(baseline) == {"known-rule"}
    assert fuzz.load_baseline(tmp_path / "absent.json") == set()

    known = fuzz.Finding("known-rule", "invariant", "d")
    known.observe({"seed": 1, "scenario": "a", "profile": "clean",
                   "version": "3.5.0", "mci": 0})
    assert fuzz.report({"known-rule": known}, {"known-rule"}, 10) == 0

    fresh = fuzz.Finding("brand-new", "invariant", "d")
    fresh.observe({"seed": 1, "scenario": "a", "profile": "clean",
                   "version": "3.5.0", "mci": 0})
    assert fuzz.report({"brand-new": fresh}, {"known-rule"}, 10) == 1
    assert "NEW" in capsys.readouterr().out


def test_no_findings_exits_clean():
    assert fuzz.report({}, set(), 100) == 0


def test_sweep_end_to_end_finds_an_injected_defect(monkeypatch):
    """The proof that the sweep can fail at all.

    It currently reports zero findings across tens of thousands of documents,
    and a harness that cannot report a defect looks exactly the same. So break
    one deliberately and require the sweep to catch, deduplicate and report it.
    """
    pytest.importorskip("nemsynth", reason="generator is an optional dev dep")

    real = fuzz._one_case

    def broken(case):
        results = real(case)
        return results + [("injected:defect", "invariant", "deliberate")]

    monkeypatch.setattr(fuzz, "_one_case", broken)
    cases = fuzz.plan(6, ["chest-pain"], ["clean"], ["3.5.0"], 0, 1)
    # jobs=1 keeps it in-process so monkeypatch applies; the parallel path is
    # exercised by the real sweeps.
    findings = fuzz.sweep(cases, jobs=1)
    assert "injected:defect" in findings
    assert findings["injected:defect"].count == 6
    assert fuzz.report(findings, set(), len(cases)) == 1


def test_real_sweep_of_generated_documents_is_clean():
    """A small live sweep, so the suite notices if the generator and the mapper
    stop agreeing — without waiting for the scheduled run."""
    pytest.importorskip("nemsynth", reason="generator is an optional dev dep")
    cases = fuzz.plan(24, ["mixed"], ["clean", "high"], ["3.5.0", "3.5.1"],
                      mci=3, seed_start=1)
    findings = fuzz.sweep(cases, jobs=1)
    assert findings == {}, f"sweep found: {sorted(findings)}"


def test_the_sweep_exercises_both_the_resolved_and_absent_paths():
    """Half the cases carry a roster and half do not, and that has to be
    visible in the output rather than assumed.

    Without a roster a PCR yields an anonymous Organization and no city at all,
    because NEMSIS names none of them: it carries an agency number, a crew
    licensure id and a GNIS code. Sweeping only that path would leave the
    resolved branch — named Organization, named Practitioner, resolved city —
    completely untested, which is what it was until this landed.
    """
    pytest.importorskip("nemsynth", reason="generator is an optional dev dep")
    from emsinterop.convert import convert
    from nemsynth.generate import generate_one

    roster = fuzz._roster()
    assert roster["city_gazetteer"], "no gazetteer to resolve with"

    def snapshot(**kwargs):
        result = convert(generate_one(1, "chest-pain", profile="clean"), **kwargs)[0]
        cities, names = set(), set()
        for resource in result.resources:
            for address in resource.get("address") or []:
                if isinstance(address, dict) and address.get("city"):
                    cities.add(address["city"])
            if resource["resourceType"] == "Organization" and resource.get("name"):
                names.add(resource["name"])
        return cities, names

    resolved_cities, resolved_names = snapshot(**roster)
    absent_cities, absent_names = snapshot()

    assert resolved_cities, "the gazetteer path produced no city at all"
    assert all(not c.isdigit() for c in resolved_cities), (
        f"a GNIS code reached Address.city: {resolved_cities}")
    assert resolved_names, "the roster path produced no Organization name"

    assert not absent_cities, (
        f"city populated without a gazetteer — from what? {absent_cities}")
    assert not absent_names, "Organization named without a roster"

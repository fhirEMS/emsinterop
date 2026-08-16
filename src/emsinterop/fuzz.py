"""Corpus sweep: generate NEMSIS at volume, convert it, triage what falls out.

The first three phases of `nemsynth` exist for this. A generator that produces
one document proves nothing; a generator that produces fifty thousand across
fifteen presentations, four messiness profiles and two releases reaches branch
combinations nobody would think to write a fixture for. Every defect this
project has found in the last two rounds was found exactly that way.

Three things make the output usable rather than a wall of noise:

**Deduplication.** A single defect in a shared code path fires on every
document that reaches it. Findings collapse to a stable signature — the rule
id, or the exception type plus the innermost frame inside this package — so
ten thousand documents produce a handful of findings, not ten thousand.

**Reproduction.** Every finding carries the exact seed, scenario, profile and
release that produced it, and nemsynth is byte-reproducible for a given seed.
A finding you cannot replay is a rumour.

**A baseline.** Known findings live in a file; the sweep exits non-zero only
for signatures that are not in it. That is what lets this run unattended
without either crying wolf or going quiet.

The direction of dependency matters: this lives in emsinterop and imports
nemsynth, never the reverse. A generator that imported its consumer's
assumptions could only ever generate what that consumer already handles.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import invariants
from .convert import convert

#: Signatures already known and accepted. Anything outside this set is new.
DEFAULT_BASELINE = Path(__file__).resolve().parents[2] / "tests" / "fuzz-baseline.json"


@dataclass
class Finding:
    """One deduplicated defect, with everything needed to reproduce it."""

    signature: str
    kind: str                       # "crash" | "invariant"
    detail: str
    count: int = 0
    examples: list[dict] = field(default_factory=list)

    def observe(self, case: dict) -> None:
        self.count += 1
        if len(self.examples) < 3:      # enough to see a pattern, not a dump
            self.examples.append(case)

    def reproduce(self) -> str:
        if not self.examples:
            return ""
        case = self.examples[0]
        if case.get("mci"):
            return (f"nemsynth gen --seed {case['seed']} --count 1 "
                    f"--mci {case['mci']} --messiness {case['profile']} "
                    f"--version {case['version']} -o out/")
        return (f"nemsynth gen --seed {case['seed']} --count 1 "
                f"--scenario {case['scenario']} --messiness {case['profile']} "
                f"--version {case['version']} -o out/")


def _crash_signature(exc: BaseException) -> str:
    """Innermost frame inside this package, so the signature names OUR code.

    Keyed on the mapper's own line rather than the exception message: messages
    interpolate values that differ per document, which would defeat the whole
    point of deduplicating."""
    frames = [f for f in traceback.extract_tb(exc.__traceback__)
              if "emsinterop" in f.filename and "/fuzz.py" not in f.filename]
    where = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else "?"
    return f"crash:{type(exc).__name__}:{where}"


def _one_case(case: dict) -> list[tuple[str, str, str]]:
    """Generate one document and convert it. Returns (signature, kind, detail).

    Runs in a worker process, so it returns plain tuples rather than objects
    and never raises: a crash here is the payload, not a failure of the sweep.
    """
    from nemsynth.generate import generate_mci, generate_one, scenario_for

    try:
        if case.get("mci"):
            document = generate_mci(case["seed"], case["mci"], case["version"],
                                    profile=case["profile"])
        else:
            # 'mixed' is resolved here, not in the plan: keeping it symbolic
            # means a finding's reproduction line says --scenario mixed, which
            # is what a human would actually re-run.
            document = generate_one(
                case["seed"], scenario_for(case["seed"], case["scenario"]),
                case["version"], profile=case["profile"])
    except Exception as exc:                                # generator defect
        return [(f"generator:{type(exc).__name__}", "generator", str(exc)[:200])]

    out = []
    try:
        # Pair the records with the agency roster: names, crew, contact and the
        # GNIS gazetteer. Without it the sweep only ever exercises the
        # absent-data path — no named Organization, anonymous Practitioners,
        # and an Address.city that is never populated.
        roster = _roster() if case["seed"] % 2 == 0 else {}
        for result in convert(document, **roster):
            for violation in invariants.check(result):
                out.append((violation.signature(), "invariant",
                            f"{violation.rule}: {violation.detail}"[:200]))
    except Exception as exc:
        out.append((_crash_signature(exc), "crash",
                    f"{type(exc).__name__}: {exc}"[:200]))
    return out


def _roster() -> dict:
    """Everything a deployment supplies alongside the records, once per worker.

    A PCR names its agency by number, its crew by licensure id and its cities
    by GNIS code, and carries none of the corresponding names. Sweeping without
    them exercises only the absent-data path: no named Organization, anonymous
    Practitioners, and an `Address.city` that is never populated. Half the
    cases run with this and half without, because both are real deployments and
    neither is the "normal" one.

    Cached because it is identical for every case — the whole corpus belongs to
    one agency — and regenerating it per document would dominate the runtime
    for no added coverage.
    """
    global _ROSTER_CACHE
    if _ROSTER_CACHE is None:
        from nemsynth.dem import generate_dem
        from nemsynth.gnis import gazetteer

        from .ingest.demographics import (agency_contact, agency_names,
                                          personnel_names)
        dem = generate_dem(seed=1)
        _ROSTER_CACHE = {
            "agency_names": agency_names(dem),
            "personnel_names": personnel_names(dem),
            "agency_contact": agency_contact(dem),
            "city_gazetteer": gazetteer(),
        }
    return _ROSTER_CACHE


_ROSTER_CACHE: dict | None = None


def plan(count: int, scenarios: list[str], profiles: list[str],
         versions: list[str], mci: int, seed_start: int) -> list[dict]:
    """The cases to run, rotated so a small sweep still covers every axis.

    Rotating rather than sampling: `--count 200` then contains every
    combination in a known proportion, and case #137 is the same case on every
    machine and every run."""
    cases = []
    for offset in range(count):
        seed = seed_start + offset
        case = {
            "seed": seed,
            "scenario": scenarios[offset % len(scenarios)],
            "profile": profiles[offset % len(profiles)],
            "version": versions[offset % len(versions)],
            "mci": 0,
        }
        # Every Nth case is a mass-casualty dataset, so the multi-report path
        # is swept without needing a separate run.
        if mci and offset % 10 == 9:
            case["mci"] = mci
        cases.append(case)
    return cases


def sweep(cases: list[dict], jobs: int = 0) -> dict[str, Finding]:
    """Run every case and collapse the results into deduplicated findings.

    `jobs=1` runs in-process rather than spawning a single worker: a real
    traceback in the parent is worth far more than parallelism when you are
    chasing down what a finding actually means.
    """
    findings: dict[str, Finding] = {}

    if jobs == 1:
        outcomes = map(_one_case, cases)
        for case, results in zip(cases, outcomes):
            _collect(findings, case, results)
        return findings

    with ProcessPoolExecutor(max_workers=jobs or None) as pool:
        for case, results in zip(cases, pool.map(_one_case, cases, chunksize=8)):
            _collect(findings, case, results)
    return findings


def _collect(findings: dict[str, Finding], case: dict,
             results: list[tuple[str, str, str]]) -> None:
    for signature, kind, detail in results:
        finding = findings.get(signature)
        if finding is None:
            finding = findings[signature] = Finding(signature, kind, detail)
        finding.observe(case)


def load_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text()).get("accepted", []))


def report(findings: dict[str, Finding], baseline: set[str], total: int) -> int:
    """Print a triaged summary. Exit code is the answer to 'is this new?'."""
    fresh = {s: f for s, f in findings.items() if s not in baseline}
    known = {s: f for s, f in findings.items() if s in baseline}

    print(f"\nswept {total} case(s)")
    print(f"  findings: {len(findings)} distinct "
          f"({len(fresh)} new, {len(known)} known)")

    for label, group in (("NEW", fresh), ("known", known)):
        if not group:
            continue
        print(f"\n{label}:")
        for finding in sorted(group.values(), key=lambda f: -f.count):
            print(f"  [{finding.kind}] {finding.signature}")
            print(f"      {finding.detail}")
            print(f"      hit {finding.count}x  e.g. {finding.reproduce()}")

    if fresh:
        print(f"\n{len(fresh)} new signature(s). Triage, fix, or add to the "
              f"baseline with a reason.")
        return 1
    print("\nno new findings.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m emsinterop.fuzz",
        description="Sweep generated NEMSIS corpora through the mapper.")
    parser.add_argument("--count", type=int, default=200,
                        help="number of cases (default 200)")
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--scenarios", default="mixed",
                        help="comma-separated, or 'mixed' (default)")
    parser.add_argument("--profiles", default="clean,low,medium,high")
    parser.add_argument("--versions", default="3.5.0,3.5.1")
    parser.add_argument("--mci", type=int, default=5,
                        help="patients per MCI case; 0 disables (default 5)")
    parser.add_argument("--jobs", type=int, default=0,
                        help="worker processes (default: CPU count - 1)")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write-baseline", action="store_true",
                        help="record every finding as accepted, then exit 0")
    args = parser.parse_args(argv)

    try:
        import nemsynth  # noqa: F401
    except ImportError:
        print("nemsynth is not installed. It is a separate public repo:\n"
              "  pip install git+https://github.com/fhirEMS/nemsynth",
              file=sys.stderr)
        return 2

    import os
    jobs = args.jobs or max(1, (os.cpu_count() or 2) - 1)
    cases = plan(args.count, args.scenarios.split(","), args.profiles.split(","),
                 args.versions.split(","), args.mci, args.seed_start)
    print(f"sweeping {len(cases)} cases on {jobs} worker(s)...", flush=True)
    findings = sweep(cases, jobs)

    if args.write_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(
            {"accepted": sorted(findings),
             "note": "Signatures accepted as known. Each needs a reason in "
                     "the PR that adds it — a baseline nobody defends is just "
                     "a mute button.",
             "detail": {s: asdict(f) for s, f in findings.items()}},
            indent=2) + "\n")
        print(f"wrote baseline with {len(findings)} signature(s) to {args.baseline}")
        return 0

    return report(findings, load_baseline(args.baseline), len(cases))


if __name__ == "__main__":
    sys.exit(main())

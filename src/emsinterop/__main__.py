"""CLI: convert a NEMSIS EMSDataSet file and print or submit the result.

  python -m emsinterop convert path/to/pcr.xml            # transaction bundle to stdout
  python -m emsinterop convert path/to/pcr.xml --document # mPSC document bundle
  python -m emsinterop convert path/to/pcr.xml --submit http://localhost:8080
  python -m emsinterop convert path/to/pcr.xml --dem dem.xml  # agency names from DEMDataSet
  python -m emsinterop validate path/to/pcr.xml           # XSD check only
"""

from __future__ import annotations

import argparse
import json
import sys

from .convert import convert
from .ingest import to_operation_outcome, validate
from .submit import FhirEngineClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="emsinterop")
    sub = parser.add_subparsers(dest="command", required=True)

    p_convert = sub.add_parser("convert", help="convert NEMSIS XML to FHIR")
    p_convert.add_argument("xml")
    p_convert.add_argument("--document", action="store_true", help="print the mPSC document bundle")
    p_convert.add_argument("--iti65", action="store_true", help="print the ITI-65 Provide Document Bundle")
    p_convert.add_argument(
        "--adt", nargs="?", const="completed", choices=["completed", "both", "prearrival"],
        help="print HL7 v2 ADT per policy: completed A03 only (default), "
             "both (A04 then A03), or prearrival A04 only")
    p_convert.add_argument("--variant", choices=["CR", "CS"], default="CR")
    p_convert.add_argument(
        "--dem",
        metavar="DEM_XML",
        help="NEMSIS DEMDataSet file supplying agency names (dAgency.03) for the Organization",
    )
    p_convert.add_argument("--config", metavar="CONFIG_JSON",
                           help="messaging config (mode fhir|adt|both + per-rail policy); "
                                "dispatches per config and prints the delivery report")
    p_convert.add_argument("--submit", metavar="BASE_URL", help="POST the transaction to fhirEngine")
    p_convert.add_argument("--token", help="bearer token for --submit")
    p_convert.add_argument("--issues", action="store_true", help="print the conversion issue log to stderr")
    p_convert.add_argument("--issues-out", metavar="JSONL",
                           help="append the conversion issue log to a JSONL file (gap-register feed)")

    p_validate = sub.add_parser("validate", help="XSD-validate NEMSIS XML")
    p_validate.add_argument("xml")

    p_land = sub.add_parser("land", help="land NEMSIS XML in the raw bronze Delta table")
    p_land.add_argument("xml")
    p_land.add_argument("table", help="path to the bronze Delta table")

    p_pkg = sub.add_parser(
        "package-ig",
        help="write the NEMSIS terminology + conformance artifacts as an unpacked "
             "FHIR package (installable via fhirEngine's install-ig)")
    p_pkg.add_argument("out_dir", help="directory to write the package into")

    p_reconcile = sub.add_parser(
        "reconcile",
        help="reconcile the conversion issue log against fhirEngine's dead-letter "
             "tables: replay raw-NEMSIS bronze and join by resource id / PCR identifier")
    p_reconcile.add_argument("bronze", help="path to the raw-NEMSIS bronze Delta table")
    p_reconcile.add_argument("delta_base", help="fhirEngine FHIRENGINE_DELTA_BASE directory")
    p_reconcile.add_argument("--out", metavar="JSON", help="write the gap register here instead of stdout")

    p_deid = sub.add_parser(
        "deid",
        help="materialize the Safe Harbor de-identified analytics projection "
             "(encounters + vitals Delta tables) from fhirEngine's Delta store")
    p_deid.add_argument("delta_base", help="fhirEngine FHIRENGINE_DELTA_BASE directory")
    p_deid.add_argument("out_dir", help="directory for the projection Delta tables")
    p_deid.add_argument("--salt", help="stable pseudonym salt for cross-run linkage "
                                       "(default: random per run)")

    p_serve = sub.add_parser(
        "serve",
        help="run the at-the-door push endpoint (POST /push: NEMSIS XML in, "
             "converted + dispatched per --config in real time)")
    p_serve.add_argument("--config", metavar="CONFIG_JSON",
                         help="messaging config; defaults to mode=fhir with no endpoints")
    p_serve.add_argument("--bronze", metavar="TABLE",
                         help="land pushed XML in this raw-NEMSIS bronze Delta table first")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8096)

    p_outcome = sub.add_parser(
        "outcome",
        help="match a hospital discharge event (ADT^A03 or FHIR Discharge "
             "Summary document) to a PCR and write back eOutcome")
    p_outcome.add_argument(
        "adt", metavar="discharge",
        help="hospital discharge event: ADT^A03 ER7 file, or a FHIR Discharge "
             "Summary document Bundle (JSON — detected by content)")
    p_outcome.add_argument("pcr", nargs="+", help="candidate PCR XML file(s)")
    p_outcome.add_argument("--apply", metavar="OUT_XML",
                           help="write the corrected PCR here when exactly one candidate LINKS")

    args = parser.parse_args(argv)

    if args.command == "validate":
        errors = validate(args.xml)
        print(json.dumps(to_operation_outcome(errors), indent=2))
        return 1 if errors else 0

    if args.command == "land":
        from .ingest.bronze import land
        written = land(args.xml, args.table)
        print(json.dumps({"landed_rows": written, "table": args.table}))
        return 0

    if args.command == "package-ig":
        from .terminology.igpackage import build_package
        print(json.dumps(build_package(args.out_dir), indent=2))
        return 0

    if args.command == "deid":
        from .analytics import project
        print(json.dumps(project(args.delta_base, args.out_dir, salt=args.salt)))
        return 0

    if args.command == "reconcile":
        from pathlib import Path
        from .reconcile import reconcile_bronze
        register = reconcile_bronze(args.bronze, args.delta_base)
        rendered = json.dumps(register, indent=2)
        if args.out:
            Path(args.out).write_text(rendered + "\n")
        else:
            print(rendered)
        return 0

    if args.command == "serve":
        from .config import MessagingConfig
        from .serve import create_app, run
        config = MessagingConfig.from_file(args.config) if args.config else None
        run(create_app(config, bronze_table=args.bronze),
            host=args.host, port=args.port)
        return 0

    if args.command == "outcome":
        from pathlib import Path
        from .ingest import parse
        from .outcome import (apply_outcome, outcome_record,
                              outcome_record_from_fhir, parse_adt, score_match)
        raw = Path(args.adt).read_text()
        if raw.lstrip().startswith("{"):
            record = outcome_record_from_fhir(json.loads(raw))
        else:
            record = outcome_record(parse_adt(raw))
        linked = []
        for pcr_path in args.pcr:
            pcr = parse(pcr_path).reports[0]
            result = score_match(pcr, record)
            print(json.dumps({"pcr": pcr_path, "pcr_number": pcr.pcr_number,
                              "verdict": result.verdict.value,
                              "signals": result.signals}))
            if result.linked:
                linked.append(pcr_path)
        if args.apply:
            if len(linked) != 1:
                print(json.dumps({"error": f"--apply requires exactly one LINKED candidate, got {len(linked)}"}),
                      file=sys.stderr)
                return 1
            corrected = apply_outcome(Path(linked[0]).read_bytes(), record)
            Path(args.apply).write_bytes(corrected)
            print(json.dumps({"applied": linked[0], "out": args.apply}))
        return 0

    names = None
    if args.dem:
        from .ingest import validate_dem
        from .ingest.demographics import agency_names

        dem_errors = validate_dem(args.dem)
        if dem_errors:
            print(json.dumps(to_operation_outcome(dem_errors), indent=2), file=sys.stderr)
            return 1
        names = agency_names(args.dem)

    results = convert(args.xml, document_variant=args.variant, agency_names=names)

    def flush_issues(exit_code: int = 0) -> int:
        for result in results:
            if args.issues:
                for issue in result.issues.issues:
                    print(
                        f"[{issue.severity}] {issue.element_id} ({issue.disposition.value}): {issue.reason}",
                        file=sys.stderr,
                    )
            if args.issues_out:
                result.issues.write_jsonl(args.issues_out)
        return exit_code

    if args.config:
        from .config import MessagingConfig, dispatch
        config = MessagingConfig.from_file(args.config)
        failed = False
        for result in results:
            report = dispatch(result, config)
            for entry in report:
                summary = {k: v for k, v in entry.items() if k != "artifact"}
                summary["artifact_kind"] = entry["kind"]
                print(json.dumps(summary))
                failed = failed or "error" in entry
        return flush_issues(1 if failed else 0)
    for result in results:
        if args.submit:
            from .issues import issues_from_operation_outcome
            from .submit import SubmissionError
            client = FhirEngineClient(args.submit, token=args.token)
            try:
                response = client.submit(result.transaction)
            except SubmissionError as error:
                # Atomic rejection — nothing dead-lettered server-side, so the
                # OperationOutcome is captured into the issue log here.
                result.issues.extend(issues_from_operation_outcome(
                    error.operation_outcome, result.context.pcr_number,
                    error.status_code))
                if error.operation_outcome is not None:
                    print(json.dumps(error.operation_outcome, indent=2), file=sys.stderr)
                return flush_issues(1)
            print(json.dumps(response, indent=2))
        elif args.adt:
            from .assemble.adt import AdtConfig, build_adt_messages
            config = AdtConfig(
                send_completed=args.adt in ("completed", "both"),
                send_prearrival=args.adt in ("prearrival", "both"),
            )
            for _event, message in build_adt_messages(result.context, config):
                sys.stdout.write(message.replace("\r", "\n"))
        else:
            if args.iti65:
                from .transport import provide_document_bundle
                payload = provide_document_bundle(result)
            elif args.document:
                payload = result.document
            else:
                payload = result.transaction
            print(json.dumps(payload, indent=2))
    return flush_issues(0)


if __name__ == "__main__":
    raise SystemExit(main())

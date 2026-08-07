"""CLI: convert a NEMSIS EMSDataSet file and print or submit the result.

  python -m nemsis2fhir convert path/to/pcr.xml            # transaction bundle to stdout
  python -m nemsis2fhir convert path/to/pcr.xml --document # mPSC document bundle
  python -m nemsis2fhir convert path/to/pcr.xml --submit http://localhost:8080
  python -m nemsis2fhir validate path/to/pcr.xml           # XSD check only
"""

from __future__ import annotations

import argparse
import json
import sys

from .convert import convert
from .ingest import to_operation_outcome, validate
from .submit import FhirEngineClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nemsis2fhir")
    sub = parser.add_subparsers(dest="command", required=True)

    p_convert = sub.add_parser("convert", help="convert NEMSIS XML to FHIR")
    p_convert.add_argument("xml")
    p_convert.add_argument("--document", action="store_true", help="print the mPSC document bundle")
    p_convert.add_argument("--iti65", action="store_true", help="print the ITI-65 Provide Document Bundle")
    p_convert.add_argument("--variant", choices=["CR", "CS"], default="CR")
    p_convert.add_argument("--submit", metavar="BASE_URL", help="POST the transaction to fhirEngine")
    p_convert.add_argument("--token", help="bearer token for --submit")
    p_convert.add_argument("--issues", action="store_true", help="print the conversion issue log to stderr")

    p_validate = sub.add_parser("validate", help="XSD-validate NEMSIS XML")
    p_validate.add_argument("xml")

    p_land = sub.add_parser("land", help="land NEMSIS XML in the raw bronze Delta table")
    p_land.add_argument("xml")
    p_land.add_argument("table", help="path to the bronze Delta table")

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

    results = convert(args.xml, document_variant=args.variant)
    for result in results:
        if args.issues:
            for issue in result.issues.issues:
                print(
                    f"[{issue.severity}] {issue.element_id} ({issue.disposition.value}): {issue.reason}",
                    file=sys.stderr,
                )
        if args.submit:
            client = FhirEngineClient(args.submit, token=args.token)
            response = client.submit(result.transaction)
            print(json.dumps(response, indent=2))
        else:
            if args.iti65:
                from .transport import provide_document_bundle
                payload = provide_document_bundle(result)
            elif args.document:
                payload = result.document
            else:
                payload = result.transaction
            print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

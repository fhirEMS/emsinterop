#!/usr/bin/env bash
# Tier-2: authoritative conformance verdict via the official HL7 validator
# (Architecture §5.5b). Generates the mPSC document bundle for every golden
# fixture and validates against base R4 + US Core 6.1.0 + this repo's authored
# StructureDefinitions (maps/structuredefinitions).
#
#   ./scripts/tier2-validate.sh [output-dir]
#
# Requires: java 17+, validator_cli.jar (EMSINTEROP_VALIDATOR_JAR, default
# ~/Downloads/validator_cli.jar), hl7.fhir.us.core#6.1.0 in ~/.fhir/packages.
# Runs with -tx n/a (no terminology server) so it is hermetic; expect
# NEMSIS-CodeSystem "cannot validate" warnings — those codes are ours.
# mPSC/IPS profile validation is deferred until a pinnable mPSC package exists
# (the IG is 2.0.0-draft; docs/01 §2 warns against floating heads).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JAR="${EMSINTEROP_VALIDATOR_JAR:-$HOME/Downloads/validator_cli.jar}"
OUT="${1:-$REPO_ROOT/.tier2-out}"
mkdir -p "$OUT"

PYTHONPATH="$REPO_ROOT/src" "$REPO_ROOT/.venv/bin/python" - "$OUT" <<'EOF'
import json, glob, sys
from emsinterop.convert import convert
out = sys.argv[1]
for path in sorted(glob.glob("tests/fixtures/*.xml")):
    name = path.split("/")[-1].replace(".xml", "")
    r = convert(path, agency_names={"4901": "Wasatch Valley EMS (synthetic)"})[0]
    json.dump(r.document, open(f"{out}/{name}_document.json", "w"))
    print("wrote", name)
EOF

fail=0
for f in "$OUT"/*_document.json; do
  name=$(basename "$f" _document.json)
  verdict=$(java -jar "$JAR" "$f" -version 4.0.1 \
      -ig hl7.fhir.us.core#6.1.0 -ig "$REPO_ROOT/maps/structuredefinitions" \
      -tx n/a 2>&1 | grep -E "FAILURE|Success:" | head -1)
  echo "$name: $verdict"
  [[ "$verdict" == *FAILURE* ]] && fail=1
done
exit $fail

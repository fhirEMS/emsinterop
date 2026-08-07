#!/usr/bin/env bash
# CI fidelity oracle (ADR-002): execute the authored FML StructureMaps on the
# reference Java engine (validator_cli — the same jar Tier-2 uses; Java is
# CI-only, never in the runtime) and diff against the native Python mappers.
#
#   ./scripts/fml-oracle.sh
#
# Requires: java 17+, validator_cli.jar (NEMSIS2FHIR_VALIDATOR_JAR, default
# ~/Downloads/validator_cli.jar), and a terminology server — the validator's
# transform mode refuses to run without one. A local fhirEngine
# (NEMSIS2FHIR_ORACLE_TX or NEMSIS2FHIR_TIER1_URL, e.g. from tier1-up.sh)
# makes the oracle fully NETWORK-FREE; otherwise falls back to tx.fhir.org.
# Our ConceptMaps resolve locally via -ig either way.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
NEMSIS2FHIR_FML_ORACLE=1 .venv/bin/python -m pytest tests/test_fml_oracle.py -v

#!/usr/bin/env bash
# Stand up a local fhirEngine (dev profile, synthetic data ONLY) for Tier-1
# validation of the golden corpus, then run the Tier-1 harness:
#
#   ./scripts/tier1-up.sh                 # boot sidecar + server, install US Core
#   EMSINTEROP_TIER1_URL=http://127.0.0.1:8095 .venv/bin/python -m pytest tests/test_tier1_fhirengine.py -v
#
# Requires: the fhirEngine sibling repo (../fhirEngine), node >= 20, and the
# hl7.fhir.us.core#6.1.0 package in ~/.fhir/packages (fetched once via any
# FHIR tooling). Dev profile has auth/audit/TLS off — never point this at PHI.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FHIRENGINE="${FHIRENGINE_DIR:-$REPO_ROOT/../fhirEngine}"
SERVER_DIR="$FHIRENGINE/packages/server"
DELTA_BASE="${TIER1_DELTA_BASE:-$REPO_ROOT/.tier1-delta}"
SIDECAR_PORT="${TIER1_SIDECAR_PORT:-8077}"
SERVER_PORT="${TIER1_SERVER_PORT:-8095}"
USCORE_PKG="$HOME/.fhir/packages/hl7.fhir.us.core#6.1.0/package"

mkdir -p "$DELTA_BASE"

# 1. Python sidecar (delta-rs / DataFusion)
if [ ! -d "$SERVER_DIR/sidecar/.venv" ]; then
  python3 -m venv "$SERVER_DIR/sidecar/.venv"
  "$SERVER_DIR/sidecar/.venv/bin/pip" install -q -r "$SERVER_DIR/sidecar/requirements.txt"
fi
"$SERVER_DIR/sidecar/.venv/bin/python" "$SERVER_DIR/sidecar/delta_sidecar.py" \
  --port "$SIDECAR_PORT" --base "$DELTA_BASE" &
SIDECAR_PID=$!
sleep 2

export FHIRENGINE_DELTA_SIDECAR_URL="http://127.0.0.1:$SIDECAR_PORT"
export FHIRENGINE_DELTA_BASE="$DELTA_BASE"
export FHIRENGINE_STORAGE_MODE=single

# 2. Install US Core 6.1.0 (idempotent)
(cd "$SERVER_DIR" && npx tsx scripts/fhirengine-terminology.ts install-ig "$USCORE_PKG" hl7.fhir.us.core)

# 2b. Build + install the emsinterop.nemsis package (NEMSIS CodeSystem,
# per-element ValueSets, ConceptMaps, extension SD) so the dual-coded NEMSIS
# codings the mapper emits resolve in fhirEngine's terminology store.
NEMSIS_PKG="$REPO_ROOT/.tier1-nemsis-pkg"
PYTHON_BIN="${EMSINTEROP_PYTHON:-$REPO_ROOT/.venv/bin/python}"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN=python3
PYTHONPATH="$REPO_ROOT/src" "$PYTHON_BIN" -m emsinterop package-ig "$NEMSIS_PKG"
(cd "$SERVER_DIR" && npx tsx scripts/fhirengine-terminology.ts install-ig "$NEMSIS_PKG" emsinterop.nemsis)

# 3. Server with declared-profile enforcement
(cd "$SERVER_DIR" && PORT="$SERVER_PORT" FHIRENGINE_VALIDATION_PROFILES=declared npx tsx src/server.ts) &
SERVER_PID=$!
sleep 3

echo ""
echo "fhirEngine Tier-1 stack up:"
echo "  sidecar  pid $SIDECAR_PID  http://127.0.0.1:$SIDECAR_PORT"
echo "  server   pid $SERVER_PID   http://127.0.0.1:$SERVER_PORT"
echo "  delta    $DELTA_BASE"
echo ""
echo "Run the harness:"
echo "  EMSINTEROP_TIER1_URL=http://127.0.0.1:$SERVER_PORT .venv/bin/python -m pytest tests/test_tier1_fhirengine.py -v"
wait

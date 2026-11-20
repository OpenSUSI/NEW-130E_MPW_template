#!/usr/bin/env bash
# ==============================================================================
# Shared environment, tool discovery, and design.yaml loader for flow/*.sh
# ==============================================================================
set -euo pipefail

FLOW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$(cd "${FLOW_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

mkdir -p output/work output/gds output/reports output/logs output/package

# Load design.yaml & active pdk.yaml into environment variables
eval "$(python3 scripts/config_loader.py --shell)"

# Tool discovery (supports Linux EDA container, GCP Batch, and macOS local PoC)
export YOSYS_BIN="${YOSYS_BIN:-$(command -v yosys || true)}"
export OPENROAD_BIN="${OPENROAD_BIN:-$(command -v openroad || true)}"
export IVERILOG_BIN="${IVERILOG_BIN:-$(command -v iverilog || true)}"
export VVP_BIN="${VVP_BIN:-$(command -v vvp || true)}"

if [[ -z "${KLAYOUT_BIN:-}" ]]; then
    if command -v klayout >/dev/null 2>&1; then
        export KLAYOUT_BIN="$(command -v klayout)"
    elif [[ -x "/Applications/klayout.app/Contents/MacOS/klayout" ]]; then
        export KLAYOUT_BIN="/Applications/klayout.app/Contents/MacOS/klayout"
    else
        export KLAYOUT_BIN=""
    fi
fi

require_tool() {
    local name="$1"
    local bin="$2"
    if [[ -z "${bin}" || ! -x "${bin}" ]]; then
        echo "ERROR: Required EDA tool '${name}' not found." >&2
        exit 1
    fi
}

#!/bin/bash
# ============================================================
#  SlipSense — Run All Services (macOS / Linux)
# ============================================================
#  Starts the FastAPI backend and React (Vite) frontend
#  in parallel. Press Ctrl+C to stop both.
#
#  Usage:
#    chmod +x run-all.sh
#    ./run-all.sh
#
#  Prerequisites:
#    Run ./install.sh first to set up all dependencies.
# ============================================================

set -e

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Resolve script directory ─────────────────────────────────
ROOT="$(cd "$(dirname "$0")" && pwd)"

BACKEND_DIR="${ROOT}/backend"
FRONTEND_DIR="${ROOT}/frontend"
BACKEND_VENV="${BACKEND_DIR}/venv"

# ── Trap Ctrl+C to kill both processes ───────────────────────
cleanup() {
    echo ""
    echo -e "${YELLOW}[STOP]${NC} Shutting down SlipSense..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null
    fi
    # Kill any child processes
    jobs -p | xargs kill 2>/dev/null
    echo -e "${GREEN}[DONE]${NC} All services stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── Preflight checks ────────────────────────────────────────
echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║          🏔️  SlipSense — Starting...          ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════╝${NC}"
echo ""

# Check backend venv
if [ ! -d "$BACKEND_VENV" ]; then
    echo -e "${RED}[FAIL]${NC} Backend virtual environment not found at: ${BACKEND_VENV}"
    echo -e "       Run ${CYAN}./install.sh${NC} first to set up dependencies."
    exit 1
fi

# Check frontend node_modules
if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
    echo -e "${RED}[FAIL]${NC} Frontend node_modules not found."
    echo -e "       Run ${CYAN}./install.sh${NC} first, or: cd frontend && npm install"
    exit 1
fi

# ============================================================
#  Start Backend (FastAPI + Uvicorn)
# ============================================================
echo -e "${CYAN}[1/2]${NC} Starting backend server..."

(
    cd "$BACKEND_DIR"
    source "${BACKEND_VENV}/bin/activate"
    python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000 2>&1 | \
        sed "s/^/  ${CYAN}[backend]${NC} /"
) &
BACKEND_PID=$!

# Give backend a few seconds to start
sleep 3

# ============================================================
#  Start Frontend (Vite dev server)
# ============================================================
echo -e "${CYAN}[2/2]${NC} Starting frontend dev server..."

(
    cd "$FRONTEND_DIR"
    npm run dev 2>&1 | \
        sed "s/^/  ${GREEN}[frontend]${NC} /"
) &
FRONTEND_PID=$!

# ============================================================
#  Running — show info
# ============================================================
sleep 2
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ SlipSense is running!                      ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  🌐 Backend API:  ${CYAN}http://localhost:8000${NC}"
echo -e "  🖥️  Frontend UI:  ${CYAN}http://localhost:5173${NC}"
echo -e "  📖 API Docs:     ${CYAN}http://localhost:8000/docs${NC}"
echo ""
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop all services."
echo ""

# ── Wait for both processes ──────────────────────────────────
wait

#!/bin/bash
# ============================================================
#  SlipSense — Full Installation Script (macOS / Linux)
# ============================================================
#  This script installs all dependencies for the SlipSense
#  landslide prediction system:
#    • Python 3.12 virtual environments (ML pipeline + backend)
#    • Node.js / npm packages (React frontend)
#    • GDAL system library (required by rasterio)
#
#  Usage:
#    chmod +x install.sh
#    ./install.sh
# ============================================================

set -e  # Exit on any error

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Colour

# ── Helper functions ─────────────────────────────────────────
info()    { echo -e "${CYAN}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[  OK]${NC}  $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $1"; exit 1; }

# ── Resolve script directory ─────────────────────────────────
ROOT="$(cd "$(dirname "$0")" && pwd)"
info "Project root: ${BOLD}${ROOT}${NC}"

# ============================================================
#  1. System-Level Prerequisites
# ============================================================
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Step 1 / 4 — Checking System Prerequisites  ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"

# ── Python ───────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PY=$(command -v python3)
    PY_VER=$($PY --version 2>&1 | awk '{print $2}')
    success "Python found: $PY ($PY_VER)"
else
    fail "Python 3 is not installed. Install it with:  brew install python@3.12"
fi

# ── Node.js / npm ────────────────────────────────────────────
if command -v node &>/dev/null; then
    NODE_VER=$(node --version)
    success "Node.js found: $(command -v node) ($NODE_VER)"
else
    fail "Node.js is not installed. Install it with:  brew install node"
fi

if command -v npm &>/dev/null; then
    NPM_VER=$(npm --version)
    success "npm found: $(command -v npm) ($NPM_VER)"
else
    fail "npm is not installed. It should come with Node.js."
fi

# ── pip ──────────────────────────────────────────────────────
if $PY -m pip --version &>/dev/null; then
    success "pip found"
else
    warn "pip not found — attempting to install..."
    $PY -m ensurepip --upgrade || fail "Could not install pip. Please install it manually."
fi

# ── GDAL (required by rasterio) ──────────────────────────────
if command -v brew &>/dev/null; then
    if brew list gdal &>/dev/null 2>&1; then
        success "GDAL installed via Homebrew"
    else
        info "Installing GDAL via Homebrew (required by rasterio)..."
        brew install gdal || warn "GDAL install failed — rasterio may still work if wheels are available"
    fi
else
    warn "Homebrew not found. If rasterio fails to install, run: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\" && brew install gdal"
fi

# ============================================================
#  2. ML Pipeline Virtual Environment
# ============================================================
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Step 2 / 4 — ML Pipeline Environment        ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"

ML_DIR="${ROOT}/ml_models"
ML_VENV="${ML_DIR}/venv"

if [ -d "$ML_VENV" ]; then
    warn "ML venv already exists at ${ML_VENV} — skipping creation"
else
    info "Creating virtual environment at ${ML_VENV}..."
    $PY -m venv "$ML_VENV"
    success "Virtual environment created"
fi

info "Activating ML venv and installing dependencies..."
source "${ML_VENV}/bin/activate"

pip install --upgrade pip setuptools wheel 2>&1 | tail -1
info "Installing ML requirements (this may take several minutes)..."
pip install -r "${ML_DIR}/requirements.txt" 2>&1 | tail -5

deactivate
success "ML pipeline dependencies installed"

# ============================================================
#  3. Backend Virtual Environment
# ============================================================
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Step 3 / 4 — Backend Environment             ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"

BACKEND_DIR="${ROOT}/backend"
BACKEND_VENV="${BACKEND_DIR}/venv"

if [ -d "$BACKEND_VENV" ]; then
    warn "Backend venv already exists at ${BACKEND_VENV} — skipping creation"
else
    info "Creating virtual environment at ${BACKEND_VENV}..."
    $PY -m venv "$BACKEND_VENV"
    success "Virtual environment created"
fi

info "Activating backend venv and installing dependencies..."
source "${BACKEND_VENV}/bin/activate"

pip install --upgrade pip setuptools wheel 2>&1 | tail -1
info "Installing backend requirements..."
pip install -r "${BACKEND_DIR}/requirements.txt" 2>&1 | tail -5

deactivate
success "Backend dependencies installed"

# ============================================================
#  4. Frontend (Node.js / npm)
# ============================================================
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Step 4 / 4 — Frontend Dependencies           ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"

FRONTEND_DIR="${ROOT}/frontend"

info "Installing npm packages..."
cd "$FRONTEND_DIR"
npm install 2>&1 | tail -5
cd "$ROOT"

success "Frontend dependencies installed"

# ============================================================
#  5. Environment File Setup
# ============================================================
echo ""
if [ -f "${BACKEND_DIR}/.env" ]; then
    success ".env file already exists in backend/"
else
    if [ -f "${FRONTEND_DIR}/.env.example" ]; then
        info "Creating backend .env from frontend .env.example template..."
        cp "${FRONTEND_DIR}/.env.example" "${BACKEND_DIR}/.env"
        success "Created backend/.env — please edit it with your API keys"
    else
        warn "No .env file found. Create backend/.env with your API keys:"
        echo "     OPENWEATHER_API_KEY=your_key_here"
        echo "     DRY_RUN=true"
    fi
fi

# ============================================================
#  Done!
# ============================================================
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ Installation Complete!                     ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  To run the full application:"
echo -e "    ${CYAN}chmod +x run-all.sh${NC}"
echo -e "    ${CYAN}./run-all.sh${NC}"
echo ""
echo -e "  To run the ML pipeline separately:"
echo -e "    ${CYAN}cd ml_models && source venv/bin/activate${NC}"
echo -e "    ${CYAN}python data_preparation.py${NC}"
echo -e "    ${CYAN}python enhanced_model.py${NC}"
echo -e "    ${CYAN}python generate_susceptibility_map.py${NC}"
echo -e "    ${CYAN}python unet_refine.py${NC}"
echo -e "    ${CYAN}python generate_runout_and_fuse.py${NC}"
echo ""
echo -e "  Docs: ${CYAN}HOW_TO_RUN.md${NC} | ${CYAN}README.md${NC}"
echo ""

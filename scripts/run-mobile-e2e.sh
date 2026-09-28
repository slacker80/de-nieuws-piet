#!/bin/bash
set -euo pipefail

# Wrapper script voor mobiele E2E tests (sectie 9.4)

# Bepaal repo root relatief
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(dirname "$SCRIPT_DIR")

# Ga naar repo root
cd "$REPO_ROOT"

# Start Docker Compose services met build
docker compose up -d --build

# Wacht op frontend en backend ready met readiness loop
./scripts/readiness-loop.sh

# Ga naar frontend directory en voer Playwright tests uit
cd frontend
npx playwright test
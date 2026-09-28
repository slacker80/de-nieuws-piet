#!/bin/bash
# Readiness loop script voor integratietests (sectie 8.8)

# Maximaal aantal pogingen
MAX_ATTEMPTS=30
SLEEP_SECONDS=1

# Frontend URL
FRONTEND_URL="http://localhost:3000/"

# Backend health endpoint URL
BACKEND_URL="http://localhost:8000/health"

# Cleanup function for temporary files
cleanup() {
    if [ -n "$frontend_bodyfile" ]; then
        rm -f "$frontend_bodyfile"
    fi
    if [ -n "$backend_bodyfile" ]; then
        rm -f "$backend_bodyfile"
    fi
}

# Trap signals for cleanup
trap cleanup EXIT

# Wacht op frontend en backend ready
for ((i=1; i<=MAX_ATTEMPTS; i++)); do
    # Initialiseer flags
    frontend_ready=false
    backend_ready=false

    # Controleer frontend toegankelijkheid
    frontend_bodyfile=$(mktemp)
    frontend_http_code=$(curl --connect-timeout 2 --max-time 5 -sS -o "$frontend_bodyfile" -w '%{http_code}' "$FRONTEND_URL")
    if [ "$frontend_http_code" = "200" ] && grep -q "Nieuws Piet" "$frontend_bodyfile"; then
        frontend_ready=true
    fi

    # Controleer backend health endpoint toegankelijkheid
    backend_bodyfile=$(mktemp)
    backend_http_code=$(curl --connect-timeout 2 --max-time 5 -sS -o "$backend_bodyfile" -w '%{http_code}' "$BACKEND_URL")
    if [ "$backend_http_code" = "200" ]; then
        # Validate JSON with python3 -c
        if python3 -c "
import json, sys
try:
    with open('$backend_bodyfile', 'r') as f:
        payload = json.load(f)
    if payload.get('status') == 'healthy':
        sys.exit(0)
    else:
        sys.exit(1)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; then
            backend_ready=true
        fi
    fi

    # Als beide ready zijn, slaag
    if [ "$frontend_ready" = true ] && [ "$backend_ready" = true ]; then
        echo "Readiness geslaagd na $i pogingen: zowel frontend als backend zijn toegankelijk"
        exit 0
    fi

    # Als we bij de laatste poging zijn, faal
    if [ $i -eq $MAX_ATTEMPTS ]; then
        echo "Fout: Readiness niet bereikt na $MAX_ATTEMPTS pogingen"
        echo "Frontend ready: $frontend_ready"
        echo "Backend ready: $backend_ready"
        exit 1
    fi

    echo "Poging $i/$MAX_ATTEMPTS: Frontend ready=$frontend_ready, Backend ready=$backend_ready, wachten..."
    sleep $SLEEP_SECONDS
done

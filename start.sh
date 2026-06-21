#!/bin/bash
set -e

# Railway sets $PORT for the public-facing service.
# Solar API binds to $PORT (public), Optimization API runs on 8001 (internal).
SOLAR_PORT=${PORT:-8000}
OPT_PORT=8001

echo "Starting Solar Prediction API on port $SOLAR_PORT..."
uvicorn main_solar_api:app --host 0.0.0.0 --port "$SOLAR_PORT" --workers 1 &
SOLAR_PID=$!

echo "Starting Battery Optimization API on port $OPT_PORT..."
SOLAR_API_URL="http://localhost:$SOLAR_PORT" \
uvicorn optimization_api:app --host 0.0.0.0 --port "$OPT_PORT" --workers 1 &
OPT_PID=$!

# If either process dies, kill the other and exit so Railway can restart
wait -n 2>/dev/null || true
kill $SOLAR_PID $OPT_PID 2>/dev/null || true
wait

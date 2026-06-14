"""
startup.py — Local development launcher (Windows & Linux/Mac)
--------------------------------------------------------------
NOT used on AWS. On AWS, Elastic Beanstalk reads the Procfile
and launches each service directly with gunicorn/uvicorn.

Usage:
    python startup.py
"""

import subprocess
import time
import requests
import sys
import os
from pathlib import Path

BASE_DIR  = Path(__file__).parent

# ── Resolve Python / uvicorn executables ──────────────────────────────────────
# Works on Windows (venv\Scripts) and Linux/Mac (venv/bin)
IS_WINDOWS = sys.platform.startswith("win")
VENV_BIN   = BASE_DIR / "venv" / ("Scripts" if IS_WINDOWS else "bin")
PYTHON_EXE = VENV_BIN / ("python.exe" if IS_WINDOWS else "python")
UVICORN_EXE= VENV_BIN / ("uvicorn.exe" if IS_WINDOWS else "uvicorn")

# Fall back to system python/uvicorn if no venv found
if not PYTHON_EXE.exists():
    PYTHON_EXE  = Path(sys.executable)
    UVICORN_EXE = Path("uvicorn")


def start_solar_api():
    print("\n🌞 Starting Solar Prediction API  (port 8000)...")
    cmd = [str(PYTHON_EXE), str(BASE_DIR / "main_solar_api.py")]
    return subprocess.Popen(cmd, cwd=str(BASE_DIR))


def start_optimization_api():
    print("\n⚡ Starting Battery Optimization API (port 8001)...")
    cmd = [
        str(UVICORN_EXE),
        "optimization_api:app",
        "--host", "0.0.0.0",
        "--port", "8001",
        "--reload"
    ]
    return subprocess.Popen(cmd, cwd=str(BASE_DIR))


def wait_for_service(url, name, max_wait=30):
    print(f"Waiting for {name}...", end="", flush=True)
    for _ in range(max_wait):
        try:
            if requests.get(url, timeout=1).ok:
                print(" ✓ Ready!")
                return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(1)
    print(" ✗ Timeout!")
    return False


def check_initialization():
    """Confirm the solar API auto-initialized from CSV."""
    try:
        resp = requests.get("http://localhost:8000/status", timeout=5)
        if resp.ok:
            data = resp.json()
            if data.get("initialized"):
                print(f"  ✓ Auto-initialized  (window: {data.get('window_size')} hrs)")
                return True
            else:
                # Try manual init (local CSV fallback)
                print("  ⚙  Auto-init not complete — attempting manual init...")
                csv_path = str(BASE_DIR / "data" / "historical" / "historical_solar_data.csv")
                init_resp = requests.post(
                    "http://localhost:8000/initialize",
                    json={"csv_path": csv_path},
                    timeout=60
                )
                if init_resp.ok:
                    result = init_resp.json()
                    print(f"  ✓ Initialized  (window: {result.get('window_size')} hrs)")
                    return True
                else:
                    print(f"  ✗ Init failed: {init_resp.text}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    return False


def main():
    print("=" * 70)
    print("  🌞⚡ SOLAR + BATTERY OPTIMIZATION SYSTEM  (local dev)")
    print("=" * 70)

    processes = []

    # Start APIs
    processes.append(start_solar_api())
    time.sleep(3)
    processes.append(start_optimization_api())

    # Wait for readiness
    print("\n⏳ Waiting for services to start...")
    solar_ready = wait_for_service("http://localhost:8000/status", "Solar API",        30)
    opt_ready   = wait_for_service("http://localhost:8001/status", "Optimization API", 30)

    if not (solar_ready and opt_ready):
        print("\n❌ ERROR: One or more services failed to start")
        for p in processes:
            p.terminate()
        return

    # Check / trigger initialization
    time.sleep(2)
    print("\n📊 Checking Solar System initialization...")
    check_initialization()

    # Summary
    print("\n" + "=" * 70)
    print("  ✓ SYSTEM READY!")
    print("=" * 70)
    print("\n📍 Endpoints:")
    print("  Solar API:        http://localhost:8000")
    print("  Optimization API: http://localhost:8001")
    print("  Dashboard:        Open complete_dashboard.html in browser")

    print("\n📋 Next Steps:")
    print("  1. Open complete_dashboard.html in your browser")
    print("  2. Go to the 'Data Input' tab")
    print("  3. Add real-time measurements or load sample data")
    print("  4. Run optimization in the 'Optimization' tab")

    print("\n⚠️  Press Ctrl+C to stop all services\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        for p in processes:
            p.terminate()
        print("Goodbye!")


if __name__ == "__main__":
    main()
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import pandas as pd
import numpy as np
import pulp
import requests
import os
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===========================
# CONFIGURATION
# ===========================
# On AWS with merged deployment, solar API is on the same host.
# Set SOLAR_API_URL env var to point to the correct service.
# Locally:  http://localhost:8000
# AWS EB merged app: http://localhost:8000  (same instance, different port via uvicorn worker)
# AWS two separate EB envs: https://solar-env.elasticbeanstalk.com
SOLAR_API_URL = os.environ.get("SOLAR_API_URL", "http://localhost:8000")

app = FastAPI(title="Battery Optimization API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default battery parameters
BATTERY_CONFIG = {
    "E_capacity":    100.0,   # kWh
    "SOC_min":        20.0,
    "SOC_max":        90.0,
    "SOC_initial":    50.0,
    "P_charge_max":   25.0,   # kW
    "P_discharge_max":25.0,
    "eta_charge":      0.95,
    "eta_discharge":   0.95
}

# ===========================
# HELPERS
# ===========================
def get_default_tariff(hours=24):
    tariff = []
    for h in range(hours):
        hour = h % 24
        if 17 <= hour <= 21:
            import_price, export_price = 0.30, 0.15
        elif 7 <= hour <= 17:
            import_price, export_price = 0.20, 0.10
        else:
            import_price, export_price = 0.15, 0.05
        tariff.append({"import_price": import_price, "export_price": export_price})
    return tariff

# ===========================
# PYDANTIC MODELS
# ===========================
class BatteryConfig(BaseModel):
    E_capacity:     float = 100.0
    SOC_min:        float = 20.0
    SOC_max:        float = 90.0
    SOC_initial:    float = 50.0
    P_charge_max:   float = 25.0
    P_discharge_max:float = 25.0
    eta_charge:     float = 0.95
    eta_discharge:  float = 0.95

class OptimizationRequest(BaseModel):
    load_demand:    List[float]
    tariff_import:  Optional[List[float]] = None
    tariff_export:  Optional[List[float]] = None
    battery_config: Optional[BatteryConfig] = None
    hours:          int = 24

# ===========================
# OPTIMIZATION ENGINE
# ===========================
def optimize_battery(
    solar_forecast: List[float],
    load_forecast:  List[float],
    tariff_import:  List[float],
    tariff_export:  List[float],
    battery_config: Dict,
    hours:          int
):
    logger.info(f"Running optimization for {hours} hours")

    prob = pulp.LpProblem("Battery_Optimization", pulp.LpMinimize)
    time_steps = range(hours)

    P_charge    = pulp.LpVariable.dicts("P_charge",    time_steps, lowBound=0,
                                        upBound=battery_config["P_charge_max"])
    P_discharge = pulp.LpVariable.dicts("P_discharge", time_steps, lowBound=0,
                                        upBound=battery_config["P_discharge_max"])
    P_import    = pulp.LpVariable.dicts("P_import",    time_steps, lowBound=0)
    P_export    = pulp.LpVariable.dicts("P_export",    time_steps, lowBound=0)
    SOC         = pulp.LpVariable.dicts("SOC", list(time_steps) + [hours],
                                        lowBound=battery_config["SOC_min"],
                                        upBound=battery_config["SOC_max"])
    u_charge    = pulp.LpVariable.dicts("u_charge",    time_steps, cat="Binary")
    u_discharge = pulp.LpVariable.dicts("u_discharge", time_steps, cat="Binary")
    u_import    = pulp.LpVariable.dicts("u_import",    time_steps, cat="Binary")

    # Objective
    prob += pulp.lpSum([
        tariff_import[t] * P_import[t] - tariff_export[t] * P_export[t]
        for t in time_steps
    ])

    # Constraints
    for t in time_steps:
        prob += (load_forecast[t] == solar_forecast[t] + P_discharge[t] +
                 P_import[t] - P_charge[t] - P_export[t], f"PowerBalance_{t}")

        prob += (SOC[t+1] == SOC[t] +
                 (battery_config["eta_charge"] * P_charge[t] / battery_config["E_capacity"] * 100)
                 - (P_discharge[t] / (battery_config["eta_discharge"] * battery_config["E_capacity"]) * 100),
                 f"SOC_{t}")

        prob += P_charge[t]    <= u_charge[t]    * battery_config["P_charge_max"]
        prob += P_discharge[t] <= u_discharge[t] * battery_config["P_discharge_max"]

        M = 1000
        prob += P_import[t] <= u_import[t] * M
        prob += P_export[t] <= (1 - u_import[t]) * M
        prob += u_charge[t] + u_discharge[t] <= 1

    prob += SOC[0] == battery_config["SOC_initial"]

    # Solve — try SCIP first, fall back to CBC (always available)
    try:
        solver = pulp.SCIP_CMD(msg=0, timeLimit=300)
        prob.solve(solver)
    except Exception:
        logger.warning("SCIP not available, using CBC")
        prob.solve(pulp.PULP_CBC_CMD(msg=0))

    schedule = []
    for t in time_steps:
        schedule.append({
            "hour":        t,
            "P_charge":    pulp.value(P_charge[t])    or 0.0,
            "P_discharge": pulp.value(P_discharge[t]) or 0.0,
            "P_import":    pulp.value(P_import[t])    or 0.0,
            "P_export":    pulp.value(P_export[t])    or 0.0,
            "SOC":         pulp.value(SOC[t+1])       or battery_config["SOC_initial"],
            "u_charge":    int(pulp.value(u_charge[t])    or 0),
            "u_discharge": int(pulp.value(u_discharge[t]) or 0)
        })

    return {
        "status":     pulp.LpStatus[prob.status],
        "total_cost": pulp.value(prob.objective) or 0.0,
        "schedule":   schedule
    }

# ===========================
# ENDPOINTS
# ===========================
@app.get("/")
def home():
    return {
        "message":      "Battery Optimization API",
        "status":       "online",
        "solar_api_url": SOLAR_API_URL
    }

@app.get("/status")
def get_status():
    return {
        "api_status":    "online",
        "battery_config": BATTERY_CONFIG,
        "solver":        "SCIP/CBC",
        "solar_api_url": SOLAR_API_URL
    }

@app.post("/config/battery")
async def configure_battery(config: BatteryConfig):
    global BATTERY_CONFIG
    BATTERY_CONFIG = config.model_dump()
    return {"status": "updated", "config": BATTERY_CONFIG}

@app.get("/config/battery")
async def get_battery_config():
    return {"config": BATTERY_CONFIG}

@app.post("/optimize")
async def optimize(request: OptimizationRequest):
    try:
        # Fetch solar predictions from solar API
        logger.info(f"Fetching solar predictions from {SOLAR_API_URL}...")
        try:
            response = requests.get(f"{SOLAR_API_URL}/predict", timeout=30)
            if not response.ok:
                raise HTTPException(
                    status_code=502,
                    detail=f"Solar API error: {response.status_code} - {response.text}"
                )
            solar_data    = response.json()
            solar_forecast= [p / 1000 for p in solar_data['predictions'][:request.hours]]  # W → kW
        except requests.exceptions.RequestException as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to connect to Solar API at {SOLAR_API_URL}: {str(e)}"
            )

        # Tariff
        if request.tariff_import and request.tariff_export:
            if len(request.tariff_import) < request.hours or len(request.tariff_export) < request.hours:
                raise HTTPException(status_code=400, detail="Tariffs must cover the requested hours")
            tariff_import = request.tariff_import[:request.hours]
            tariff_export = request.tariff_export[:request.hours]
        else:
            default_tariff= get_default_tariff(request.hours)
            tariff_import = [t["import_price"] for t in default_tariff]
            tariff_export = [t["export_price"] for t in default_tariff]

        # Battery config
        battery_config = BATTERY_CONFIG.copy()
        if request.battery_config:
            battery_config.update(request.battery_config.model_dump())

        # Load demand
        if len(request.load_demand) < request.hours:
            raise HTTPException(status_code=400, detail="Load demand must cover the requested hours")
        load_forecast = request.load_demand[:request.hours]

        # Align lengths
        hours = request.hours
        if len(solar_forecast) != len(load_forecast):
            hours         = min(len(solar_forecast), len(load_forecast))
            logger.warning(f"Truncating forecasts to {hours} hours")
            solar_forecast= solar_forecast[:hours]
            load_forecast = load_forecast[:hours]
            tariff_import = tariff_import[:hours]
            tariff_export = tariff_export[:hours]

        # Run optimization
        try:
            results = optimize_battery(
                solar_forecast=solar_forecast,
                load_forecast=load_forecast,
                tariff_import=tariff_import,
                tariff_export=tariff_export,
                battery_config=battery_config,
                hours=hours
            )
        except Exception as e:
            logger.error(f"Optimization engine error: {e}")
            raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")

        # Augment response
        results["solar_forecast"]  = solar_forecast
        results["load_forecast"]   = load_forecast
        results["tariff_import"]   = tariff_import
        results["tariff_export"]   = tariff_export
        results["battery_config"]  = battery_config

        total_import   = sum(s["P_import"]    for s in results["schedule"])
        total_export   = sum(s["P_export"]    for s in results["schedule"])
        battery_cycles = sum(1 for s in results["schedule"] if s["u_charge"] or s["u_discharge"])

        results["summary"] = {
            "total_cost":      results["total_cost"],
            "total_import_kwh":total_import,
            "total_export_kwh":total_export,
            "battery_cycles":  battery_cycles
        }

        logger.info(f"Optimization complete. Cost: ${results['total_cost']:.2f}")
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/tariff/default")
async def get_default_tariff_endpoint(hours: int = 24):
    tariff = get_default_tariff(hours)
    return {"tariff": tariff, "hours": hours}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8001)))
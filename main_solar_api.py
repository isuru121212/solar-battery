from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import joblib
import os
import json
import logging
import requests
from pathlib import Path
from tensorflow import keras

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===========================
# CONFIGURATION
# ===========================
BASE_DIR = Path(__file__).parent

# --- AWS vs Local path resolution ---
# On AWS, set environment variables:
#   USE_S3=true
#   S3_BUCKET=your-bucket-name
USE_S3 = os.environ.get("USE_S3", "false").lower() == "true"
S3_BUCKET = os.environ.get("S3_BUCKET", "")

MODEL_DIR = Path("/tmp/models") if USE_S3 else BASE_DIR / "models"
DATA_DIR  = Path("/tmp/data")   if USE_S3 else BASE_DIR / "data" / "historical"

MODEL_PATH           = str(MODEL_DIR / "final_model_20250928_225759.keras")
CONFIG_PATH          = str(MODEL_DIR / "model_config_20250928_225800.json")
SCALER_FEATURES_PATH = str(MODEL_DIR / "scaler_features_20250928_225800.pkl")
SCALER_TARGET_PATH   = str(MODEL_DIR / "scaler_target_20250928_225800.pkl")
HISTORICAL_CSV_PATH  = str(DATA_DIR  / "historical_solar_data.csv")

LATITUDE  = 9.67
LONGITUDE = 80.18

# ===========================
# S3 DOWNLOAD HELPER
# ===========================
def download_from_s3():
    """Download model files from S3 to /tmp at startup (AWS only)."""
    import boto3
    s3 = boto3.client("s3")

    os.makedirs(str(MODEL_DIR), exist_ok=True)
    os.makedirs(str(DATA_DIR),  exist_ok=True)

    files = {
        "models/final_model_20250928_225759.keras":       MODEL_PATH,
        "models/model_config_20250928_225800.json":       CONFIG_PATH,
        "models/scaler_features_20250928_225800.pkl":     SCALER_FEATURES_PATH,
        "models/scaler_target_20250928_225800.pkl":       SCALER_TARGET_PATH,
        "data/historical/historical_solar_data.csv":      HISTORICAL_CSV_PATH,
    }

    for s3_key, local_path in files.items():
        if not os.path.exists(local_path):
            logger.info(f"Downloading s3://{S3_BUCKET}/{s3_key} → {local_path}")
            s3.download_file(S3_BUCKET, s3_key, local_path)
        else:
            logger.info(f"Already cached: {local_path}")

# ===========================
# LOAD MODELS
# ===========================
if USE_S3:
    logger.info("AWS mode — downloading assets from S3...")
    download_from_s3()

logger.info("Loading models...")
try:
    model            = keras.models.load_model(MODEL_PATH)
    scaler_features  = joblib.load(SCALER_FEATURES_PATH)
    scaler_target    = joblib.load(SCALER_TARGET_PATH)

    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    selected_feature_indices = config["selected_feature_indices"]
    sequence_length          = config.get("sequence_length", 48)

    logger.info(f"Models loaded. Sequence: {sequence_length}h")
except Exception as e:
    logger.error(f"Failed to load models: {e}")
    raise

# All 62 training features
ALL_TRAINING_FEATURES = [
    'relative_humidity_2m ', 'wind_speed_10m', 'wind_direction_10m',
    'cloud_cover_low', 'diffuse_radiation', 'diffuse_radiation_instant',
    'direct_radiation', 'direct_radiation_instant', 'direct_normal_irradiance',
    'direct_normal_irradiance_instant', 'is_day', 'hour_angle',
    'solar_azimuth_rad', 'solar_azimuth_deg', 'is_daylight',
    'solar_potential', 'wind_cooling', 'weather_clarity_index',
    'day', 'year', 'day_of_week', 'hour_sin', 'hour_cos',
    'day_year_sin', 'day_year_cos', 'day_week_sin', 'day_week_cos',
    'month_sin', 'month_cos', 'season', 'season_sin', 'season_cos',
    'is_weekend', 'is_month_start',
    'Power(W)_lag_1h', 'Power(W)_lag_2h', 'Power(W)_lag_3h',
    'Power(W)_lag_6h', 'Power(W)_lag_12h', 'Power(W)_lag_24h', 'Power(W)_lag_48h',
    'Power(W)_diff_1h', 'Power(W)_diff_24h', 'Power(W)_diff_7d',
    'Power(W)_roll_mean_3h', 'Power(W)_roll_std_3h', 'Power(W)_roll_max_3h',
    'Power(W)_roll_min_3h', 'Power(W)_roll_range_3h',
    'Power(W)_roll_mean_6h', 'Power(W)_roll_std_6h', 'Power(W)_roll_max_6h',
    'Power(W)_roll_min_6h', 'Power(W)_roll_range_6h',
    'Power(W)_roll_mean_12h', 'Power(W)_roll_std_12h', 'Power(W)_roll_max_12h',
    'Power(W)_roll_min_12h', 'Power(W)_roll_range_12h',
    'Power(W)_ewm_6h', 'Power(W)_ewm_12h', 'Power(W)_ewm_24h'
]

# ===========================
# SLIDING WINDOW MANAGER
# ===========================
class SlidingWindowManager:
    def __init__(self):
        self.window_df    = None
        self.is_initialized = False
        self.last_update  = None

    def initialize(self, df):
        if len(df) < sequence_length:
            raise ValueError(f"Need minimum {sequence_length} hours")
        self.window_df      = df.tail(sequence_length).copy()
        self.is_initialized = True
        self.last_update    = self.window_df['datetime'].max()
        logger.info(f"Window initialized with {len(self.window_df)} hours")

    def add_measurement(self, timestamp, power, weather_data=None):
        new_row = pd.DataFrame([{
            'datetime': pd.to_datetime(timestamp),
            'Power(W)': power
        }])
        if weather_data:
            for key, value in weather_data.items():
                new_row[key] = value

        self.window_df = pd.concat([self.window_df, new_row], ignore_index=True)
        self.window_df = create_all_features(self.window_df)
        self.window_df = self.window_df.tail(sequence_length)
        self.last_update = timestamp
        logger.info(f"Added measurement at {timestamp}")

sliding_window = SlidingWindowManager()

# ===========================
# AUTO-INITIALIZE ON STARTUP
# ===========================
def auto_initialize():
    """Initialize sliding window from CSV at startup (works locally and on AWS)."""
    csv_path = HISTORICAL_CSV_PATH
    if not os.path.exists(csv_path):
        logger.warning(f"Historical CSV not found at {csv_path} — skipping auto-init")
        return

    try:
        df = pd.read_csv(csv_path)
        if 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'])
        elif 'time' in df.columns:
            df['datetime'] = pd.to_datetime(df['time'])

        df = df.sort_values('datetime').reset_index(drop=True)
        df = create_all_features(df)
        sliding_window.initialize(df)
        logger.info("Auto-initialized from CSV at startup")
    except Exception as e:
        logger.warning(f"Auto-init failed: {e}")

# ===========================
# FEATURE ENGINEERING
# ===========================
def create_all_features(df):
    df = df.copy()

    if 'datetime' not in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'])

    df['hour']       = df['datetime'].dt.hour
    df['day_of_year']= df['datetime'].dt.dayofyear
    lat_rad          = np.radians(LATITUDE)

    df['solar_declination'] = 23.45 * np.sin(np.radians(360 * (284 + df['day_of_year']) / 365))
    df['hour_angle']        = 15 * (df['hour'] - 12)

    sin_elevation = (
        np.sin(np.radians(df['solar_declination'])) * np.sin(lat_rad) +
        np.cos(np.radians(df['solar_declination'])) * np.cos(lat_rad) *
        np.cos(np.radians(df['hour_angle']))
    )

    df['solar_elevation_rad'] = np.arcsin(np.clip(sin_elevation, -1, 1))
    df['solar_elevation_deg'] = np.degrees(df['solar_elevation_rad'])
    df['solar_elevation_deg'] = np.maximum(0, df['solar_elevation_deg'])

    cos_azimuth = (
        (np.sin(np.radians(df['solar_declination'])) * np.cos(lat_rad) -
         np.cos(np.radians(df['solar_declination'])) * np.sin(lat_rad) *
         np.cos(np.radians(df['hour_angle']))) /
        (np.cos(df['solar_elevation_rad']) + 1e-10)
    )

    df['solar_azimuth_rad'] = np.arccos(np.clip(cos_azimuth, -1, 1))
    df['solar_azimuth_deg'] = np.degrees(df['solar_azimuth_rad'])
    df.loc[df['hour'] > 12, 'solar_azimuth_deg'] = (
        360 - df.loc[df['hour'] > 12, 'solar_azimuth_deg']
    )

    df['is_daylight']    = (df['solar_elevation_deg'] > 0).astype(int)
    df['solar_potential']= df['solar_elevation_deg'] / 90.0

    if 'relative_humidity_2m' in df.columns and 'relative_humidity_2m ' not in df.columns:
        df['relative_humidity_2m '] = df['relative_humidity_2m']
    if 'wind_speed_10m' in df.columns:
        df['wind_cooling'] = df['wind_speed_10m'] * 0.1

    df['weather_clarity_index'] = 1.0

    df['day']        = df['datetime'].dt.day
    df['month']      = df['datetime'].dt.month
    df['year']       = df['datetime'].dt.year
    df['day_of_week']= df['datetime'].dt.dayofweek

    df['hour_sin']     = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos']     = np.cos(2 * np.pi * df['hour'] / 24)
    df['day_year_sin'] = np.sin(2 * np.pi * df['day_of_year'] / 365.25)
    df['day_year_cos'] = np.cos(2 * np.pi * df['day_of_year'] / 365.25)
    df['day_week_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['day_week_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['month_sin']    = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos']    = np.cos(2 * np.pi * df['month'] / 12)

    season_map   = {12:0,1:0,2:0,3:1,4:1,5:1,6:2,7:2,8:2,9:3,10:3,11:3}
    df['season']     = df['month'].map(season_map)
    df['season_sin'] = np.sin(2 * np.pi * df['season'] / 4)
    df['season_cos'] = np.cos(2 * np.pi * df['season'] / 4)

    df['is_weekend']    = (df['day_of_week'] >= 5).astype(int)
    df['is_month_start']= (df['day'] <= 7).astype(int)

    if 'Power(W)' in df.columns:
        for lag in [1, 2, 3, 6, 12, 24, 48]:
            df[f'Power(W)_lag_{lag}h'] = df['Power(W)'].shift(lag)
        df['Power(W)_diff_1h']  = df['Power(W)'].diff(1)
        df['Power(W)_diff_24h'] = df['Power(W)'].diff(24)
        df['Power(W)_diff_7d']  = df['Power(W)'].diff(24 * 7)
        for window in [3, 6, 12]:
            df[f'Power(W)_roll_mean_{window}h']  = df['Power(W)'].rolling(window, min_periods=1).mean()
            df[f'Power(W)_roll_std_{window}h']   = df['Power(W)'].rolling(window, min_periods=1).std()
            df[f'Power(W)_roll_max_{window}h']   = df['Power(W)'].rolling(window, min_periods=1).max()
            df[f'Power(W)_roll_min_{window}h']   = df['Power(W)'].rolling(window, min_periods=1).min()
            df[f'Power(W)_roll_range_{window}h'] = (
                df[f'Power(W)_roll_max_{window}h'] - df[f'Power(W)_roll_min_{window}h']
            )
        for span in [6, 12, 24]:
            df[f'Power(W)_ewm_{span}h'] = df['Power(W)'].ewm(span=span, adjust=False).mean()

    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isnull().any():
            df[col] = df[col].interpolate(method='linear', limit_direction='both')
            df[col] = df[col].ffill().bfill().fillna(0)

    for feature in ALL_TRAINING_FEATURES:
        if feature not in df.columns:
            df[feature] = 0

    return df

def make_prediction(window_df):
    X_all = np.zeros((len(window_df), len(ALL_TRAINING_FEATURES)))
    for i, feature_name in enumerate(ALL_TRAINING_FEATURES):
        if feature_name in window_df.columns:
            X_all[:, i] = window_df[feature_name].values

    X_scaled   = scaler_features.transform(X_all)
    X_selected = X_scaled[:, selected_feature_indices]

    if len(X_selected) < sequence_length:
        raise ValueError(f"Need {sequence_length} hours")

    X_seq      = X_selected[-sequence_length:].reshape(1, sequence_length, len(selected_feature_indices))
    pred_scaled= model.predict(X_seq, verbose=0)
    predictions= scaler_target.inverse_transform(pred_scaled.reshape(-1, 1)).flatten()
    predictions= np.maximum(0, predictions)
    return predictions

# ===========================
# FASTAPI APP
# ===========================
app = FastAPI(title="Solar Power Prediction API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Run auto-init when the app starts
@app.on_event("startup")
async def startup_event():
    auto_initialize()

# ===========================
# PYDANTIC MODELS
# ===========================
class InitializeRequest(BaseModel):
    csv_path: Optional[str] = None   # now optional — defaults to HISTORICAL_CSV_PATH

class RealtimeUpdate(BaseModel):
    timestamp: str
    power: float
    weather_data: Optional[Dict] = None

# ===========================
# ENDPOINTS
# ===========================
@app.get("/")
def home():
    return {
        "message": "Solar Power Prediction API",
        "status": "online",
        "window_size": f"{sequence_length}h",
        "mode": "AWS/S3" if USE_S3 else "local"
    }

@app.get("/status")
def get_status():
    return {
        "initialized":     sliding_window.is_initialized,
        "window_size":     len(sliding_window.window_df) if sliding_window.window_df is not None else 0,
        "last_update":     sliding_window.last_update.isoformat() if sliding_window.last_update else None,
        "sequence_length": sequence_length
    }

@app.post("/initialize")
async def initialize_system(request: InitializeRequest = None):
    """Initialize with historical data (optional body — defaults to bundled CSV)."""
    try:
        # Determine CSV path
        if request and request.csv_path:
            csv_path = request.csv_path
            if not os.path.isabs(csv_path):
                csv_path = str(DATA_DIR / csv_path)
        else:
            csv_path = HISTORICAL_CSV_PATH

        logger.info(f"Initializing with: {csv_path}")

        df = pd.read_csv(csv_path)
        if 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'])
        elif 'time' in df.columns:
            df['datetime'] = pd.to_datetime(df['time'])

        df = df.sort_values('datetime').reset_index(drop=True)
        df = create_all_features(df)
        sliding_window.initialize(df)

        return {
            "status":          "initialized",
            "window_size":     len(sliding_window.window_df),
            "last_historical": sliding_window.last_update.isoformat(),
            "date_range": {
                "start": df['datetime'].min().isoformat(),
                "end":   df['datetime'].max().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update/realtime")
async def update_realtime(update: RealtimeUpdate):
    if not sliding_window.is_initialized:
        raise HTTPException(status_code=400, detail="System not initialized")
    try:
        timestamp = pd.to_datetime(update.timestamp)
        sliding_window.add_measurement(timestamp, update.power, update.weather_data)
        return {"status": "updated", "timestamp": timestamp.isoformat(), "power": update.power}
    except Exception as e:
        logger.error(f"Update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/predict")
async def get_predictions():
    if not sliding_window.is_initialized:
        raise HTTPException(status_code=400, detail="System not initialized")
    try:
        predictions = make_prediction(sliding_window.window_df)
        start_time  = sliding_window.last_update + timedelta(hours=1)
        timestamps  = [(start_time + timedelta(hours=i)).isoformat() for i in range(len(predictions))]
        return {
            "timestamps":       timestamps,
            "predictions":      predictions.tolist(),
            "mean_power":       float(np.mean(predictions)),
            "max_power":        float(np.max(predictions)),
            "total_energy_kwh": float(np.sum(predictions) / 1000)
        }
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
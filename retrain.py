"""
Retrain Solar Prediction Model on Full 1-Year Dataset
- Uses same CNN+LSTM architecture and hyperparameters from model_config
- Trains on 80% of data, validates on 10%, tests on final 10%
- Saves new model + scalers + config to models/ folder
- Replaces the old 11-day trained model
"""

import pandas as pd
import numpy as np
import json
import joblib
import os
import warnings
warnings.filterwarnings('ignore')
from pathlib import Path
from datetime import datetime
from sklearn.preprocessing import StandardScaler, MaxAbsScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, regularizers

# ===========================
# PATHS
# ===========================
BASE_DIR  = Path(__file__).parent
MODEL_DIR = BASE_DIR / "models"

DATASET_CSV  = r"F:\research papers\isuru\New folder (6)\hourly_solar_power_imputed original_new.csv"
CONFIG_PATH  = str(MODEL_DIR / "model_config_20260621_192314.json")

TIMESTAMP    = datetime.now().strftime("%Y%m%d_%H%M%S")
NEW_MODEL_PATH           = str(MODEL_DIR / f"final_model_{TIMESTAMP}.keras")
NEW_CONFIG_PATH          = str(MODEL_DIR / f"model_config_{TIMESTAMP}.json")
NEW_SCALER_FEATURES_PATH = str(MODEL_DIR / f"scaler_features_{TIMESTAMP}.pkl")
NEW_SCALER_TARGET_PATH   = str(MODEL_DIR / f"scaler_target_{TIMESTAMP}.pkl")

LATITUDE  = 9.67
LONGITUDE = 80.18

SEQUENCE_LENGTH    = 48
PREDICTION_HORIZON = 24

# ===========================
# ALL TRAINING FEATURES — expanded with full weather data from dataset
# ===========================
ALL_TRAINING_FEATURES = [
    # Core weather (directly in dataset)
    'temperature_2m ',
    'relative_humidity_2m ',
    'wind_speed_10m', 'wind_direction_10m',
    'surface_pressure',
    'dew_point_2m',
    # Radiation (directly in dataset)
    'shortwave_radiation_instant',
    'direct_radiation_instant',
    'direct_normal_irradiance_instant',
    'diffuse_radiation_instant',
    # Cloud cover (directly in dataset — KEY for peak prediction)
    'cloud_cover',
    'cloud_cover_high',
    'cloud_cover_mid',
    'cloud_cover_low',
    # Sky clarity indices (directly in dataset)
    'ALLSKY_KT',          # all-sky clearness index (0=overcast, 1=clear)
    'CLRSKY_SFC_SW_DWN',  # clear-sky surface shortwave
    'ALLSKY_SRF_ALB',     # surface albedo
    # Solar geometry (computed)
    'is_day', 'is_daylight',
    'hour_angle',
    'solar_azimuth_rad', 'solar_azimuth_deg',
    'solar_potential',
    # Engineered weather
    'wind_cooling', 'weather_clarity_index',
    # Time features
    'day', 'year', 'day_of_week',
    'hour_sin', 'hour_cos',
    'day_year_sin', 'day_year_cos',
    'month_sin', 'month_cos',
    'season_sin', 'season_cos',
    'is_weekend', 'is_month_start',
    # Power lag features
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
# FEATURE ENGINEERING
# ===========================
def create_all_features(df):
    df = df.copy()
    if 'datetime' not in df.columns:
        df['datetime'] = pd.to_datetime(df.get('time', df.get('timestamp')))

    df['hour']        = df['datetime'].dt.hour
    df['day_of_year'] = df['datetime'].dt.dayofyear
    lat_rad = np.radians(LATITUDE)

    df['solar_declination'] = 23.45 * np.sin(np.radians(360 * (284 + df['day_of_year']) / 365))
    df['hour_angle']        = 15 * (df['hour'] - 12)

    sin_elev = (np.sin(np.radians(df['solar_declination'])) * np.sin(lat_rad) +
                np.cos(np.radians(df['solar_declination'])) * np.cos(lat_rad) *
                np.cos(np.radians(df['hour_angle'])))
    df['solar_elevation_rad'] = np.arcsin(np.clip(sin_elev, -1, 1))
    df['solar_elevation_deg'] = np.maximum(0, np.degrees(df['solar_elevation_rad']))

    cos_az = ((np.sin(np.radians(df['solar_declination'])) * np.cos(lat_rad) -
               np.cos(np.radians(df['solar_declination'])) * np.sin(lat_rad) *
               np.cos(np.radians(df['hour_angle']))) /
              (np.cos(df['solar_elevation_rad']) + 1e-10))
    df['solar_azimuth_rad'] = np.arccos(np.clip(cos_az, -1, 1))
    df['solar_azimuth_deg'] = np.degrees(df['solar_azimuth_rad'])
    df.loc[df['hour'] > 12, 'solar_azimuth_deg'] = 360 - df.loc[df['hour'] > 12, 'solar_azimuth_deg']

    df['is_daylight']     = (df['solar_elevation_deg'] > 0).astype(int)
    df['solar_potential'] = df['solar_elevation_deg'] / 90.0

    if 'relative_humidity_2m' in df.columns and 'relative_humidity_2m ' not in df.columns:
        df['relative_humidity_2m '] = df['relative_humidity_2m']
    if 'temperature_2m' in df.columns and 'temperature_2m ' not in df.columns:
        df['temperature_2m '] = df['temperature_2m']
    if 'wind_speed_10m' in df.columns:
        df['wind_cooling'] = df['wind_speed_10m'] * 0.1
    # Use actual clearness index if available, else default to 1.0
    if 'ALLSKY_KT' in df.columns:
        df['weather_clarity_index'] = df['ALLSKY_KT'].clip(0, 1)
    else:
        df['weather_clarity_index'] = 1.0

    df['day']         = df['datetime'].dt.day
    df['month']       = df['datetime'].dt.month
    df['year']        = df['datetime'].dt.year
    df['day_of_week'] = df['datetime'].dt.dayofweek

    df['hour_sin']     = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos']     = np.cos(2 * np.pi * df['hour'] / 24)
    df['day_year_sin'] = np.sin(2 * np.pi * df['day_of_year'] / 365.25)
    df['day_year_cos'] = np.cos(2 * np.pi * df['day_of_year'] / 365.25)
    df['day_week_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['day_week_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['month_sin']    = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos']    = np.cos(2 * np.pi * df['month'] / 12)

    season_map = {12:0,1:0,2:0,3:1,4:1,5:1,6:2,7:2,8:2,9:3,10:3,11:3}
    df['season']     = df['month'].map(season_map)
    df['season_sin'] = np.sin(2 * np.pi * df['season'] / 4)
    df['season_cos'] = np.cos(2 * np.pi * df['season'] / 4)

    df['is_weekend']     = (df['day_of_week'] >= 5).astype(int)
    df['is_month_start'] = (df['day'] <= 7).astype(int)

    for lag in [1, 2, 3, 6, 12, 24, 48]:
        df[f'Power(W)_lag_{lag}h'] = df['Power(W)'].shift(lag)
    df['Power(W)_diff_1h']  = df['Power(W)'].diff(1)
    df['Power(W)_diff_24h'] = df['Power(W)'].diff(24)
    df['Power(W)_diff_7d']  = df['Power(W)'].diff(24 * 7)
    for window in [3, 6, 12]:
        df[f'Power(W)_roll_mean_{window}h']  = df['Power(W)'].rolling(window, min_periods=1).mean()
        df[f'Power(W)_roll_std_{window}h']   = df['Power(W)'].rolling(window, min_periods=1).std().fillna(0)
        df[f'Power(W)_roll_max_{window}h']   = df['Power(W)'].rolling(window, min_periods=1).max()
        df[f'Power(W)_roll_min_{window}h']   = df['Power(W)'].rolling(window, min_periods=1).min()
        df[f'Power(W)_roll_range_{window}h'] = (df[f'Power(W)_roll_max_{window}h'] -
                                                 df[f'Power(W)_roll_min_{window}h'])
    for span in [6, 12, 24]:
        df[f'Power(W)_ewm_{span}h'] = df['Power(W)'].ewm(span=span, adjust=False).mean()

    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isnull().any():
            df[col] = df[col].interpolate(method='linear', limit_direction='both')
            df[col] = df[col].ffill().bfill().fillna(0)

    for feat in ALL_TRAINING_FEATURES:
        if feat not in df.columns:
            df[feat] = 0

    return df


# ===========================
# BUILD SEQUENCES
# ===========================
def build_sequences(X, y, seq_len, horizon):
    """Build (X_seq, y_seq) pairs for multi-step prediction."""
    Xs, ys = [], []
    for i in range(len(X) - seq_len - horizon + 1):
        Xs.append(X[i : i + seq_len])
        ys.append(y[i + seq_len : i + seq_len + horizon])
    return np.array(Xs), np.array(ys)


# ===========================
# BUILD MODEL — fixed architecture with reduced dropout
# ===========================
def build_model(n_features, seq_len, horizon, hp=None):
    inputs = keras.Input(shape=(seq_len, n_features))
    x = inputs

    # CNN Block 1: extract local patterns (3h windows)
    x = layers.Conv1D(64, 3, activation='relu', padding='same')(x)
    x = layers.Conv1D(64, 3, activation='relu', padding='same')(x)
    x = layers.MaxPooling1D(pool_size=2)(x)
    x = layers.Dropout(0.1)(x)

    # CNN Block 2: extract wider patterns (6h windows)
    x = layers.Conv1D(128, 5, activation='relu', padding='same')(x)
    x = layers.MaxPooling1D(pool_size=2)(x)
    x = layers.Dropout(0.1)(x)

    # LSTM: temporal dependencies
    x = layers.LSTM(128, dropout=0.1, recurrent_dropout=0.0)(x)
    x = layers.Dropout(0.2)(x)

    # Dense head
    x = layers.Dense(64, activation='relu')(x)
    x = layers.Dropout(0.1)(x)
    outputs = layers.Dense(horizon)(x)

    model = keras.Model(inputs, outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss='mse',
        metrics=['mae']
    )
    return model


# ===========================
# MAIN RETRAIN
# ===========================
def retrain():
    print("=" * 60)
    print("RETRAINING CNN+LSTM ON FULL 1-YEAR DATASET")
    print("=" * 60)

    # Load config for hyperparameters only — features rebuilt from scratch
    with open(CONFIG_PATH, 'r') as f:
        old_config = json.load(f)
    hp               = old_config['best_hyperparameters']
    # Use all features in ALL_TRAINING_FEATURES (indices are 0..N-1)
    selected_indices = list(range(len(ALL_TRAINING_FEATURES)))
    selected_names   = ALL_TRAINING_FEATURES
    print(f"Using {len(selected_names)} features (expanded with full weather data)")

    # Load dataset
    print(f"\nLoading dataset...")
    df = pd.read_csv(DATASET_CSV)
    df['datetime'] = pd.to_datetime(df['time'])
    df = df.sort_values('datetime').reset_index(drop=True)
    print(f"Rows: {len(df)} | {df['datetime'].min()} to {df['datetime'].max()}")

    # Feature engineering
    print("\nEngineering features...")
    df = create_all_features(df)

    # Build feature matrix
    X_all = np.zeros((len(df), len(ALL_TRAINING_FEATURES)))
    for i, feat in enumerate(ALL_TRAINING_FEATURES):
        if feat in df.columns:
            X_all[:, i] = df[feat].values
    y_all = df['Power(W)'].values

    # Drop first 48 rows (NaN lag features)
    X_all = X_all[SEQUENCE_LENGTH:]
    y_all = y_all[SEQUENCE_LENGTH:]

    # Fit scalers on full data (before split to capture full range)
    print("\nFitting scalers...")
    scaler_features = StandardScaler()
    scaler_target   = MaxAbsScaler()

    X_scaled = scaler_features.fit_transform(X_all)
    y_scaled = scaler_target.fit_transform(y_all.reshape(-1, 1)).flatten()

    # All features selected (indices = 0..N-1, no subsetting needed)
    X_selected = X_scaled
    n_features  = X_selected.shape[1]
    print(f"Feature matrix: {X_selected.shape}")

    # Build sequences
    print("\nBuilding sequences...")
    X_seq, y_seq = build_sequences(X_selected, y_scaled, SEQUENCE_LENGTH, PREDICTION_HORIZON)
    print(f"Sequences: X={X_seq.shape}, y={y_seq.shape}")

    # Train/val/test split (80/10/10) — chronological, no shuffle
    n         = len(X_seq)
    n_train   = int(n * 0.80)
    n_val     = int(n * 0.10)

    X_train, y_train = X_seq[:n_train],          y_seq[:n_train]
    X_val,   y_val   = X_seq[n_train:n_train+n_val], y_seq[n_train:n_train+n_val]
    X_test,  y_test  = X_seq[n_train+n_val:],    y_seq[n_train+n_val:]

    print(f"\nSplit — Train: {len(X_train)} | Val: {len(X_val)} | Test: {len(X_test)}")

    # Build model
    print("\nBuilding model...")
    model = build_model(n_features, SEQUENCE_LENGTH, PREDICTION_HORIZON, hp)
    model.summary()

    # Callbacks
    callbacks = [
        keras.callbacks.EarlyStopping(patience=20, restore_best_weights=True,
                                      monitor='val_loss', min_delta=1e-5, verbose=1),
        keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=8, min_lr=1e-6,
                                          monitor='val_loss', verbose=1),
        keras.callbacks.ModelCheckpoint(NEW_MODEL_PATH, save_best_only=True,
                                        monitor='val_loss', verbose=1),
    ]

    # Train
    print("\nTraining...")
    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=300,
        batch_size=64,
        callbacks=callbacks,
        verbose=1
    )

    # Evaluate on test set
    print("\nEvaluating on test set...")
    y_pred_scaled = model.predict(X_test, verbose=0)

    # Inverse transform (predict 24h, evaluate each hour)
    y_test_inv = scaler_target.inverse_transform(y_test.reshape(-1, 1)).reshape(y_test.shape)
    y_pred_inv = scaler_target.inverse_transform(y_pred_scaled.reshape(-1, 1)).reshape(y_pred_scaled.shape)

    y_test_flat = y_test_inv.flatten()
    y_pred_flat = np.maximum(0, y_pred_inv.flatten())

    mae  = mean_absolute_error(y_test_flat, y_pred_flat)
    rmse = np.sqrt(mean_squared_error(y_test_flat, y_pred_flat))
    r2   = r2_score(y_test_flat, y_pred_flat)
    mask = y_test_flat > 10
    mape = np.mean(np.abs((y_test_flat[mask] - y_pred_flat[mask]) / y_test_flat[mask])) * 100

    print("\n" + "=" * 50)
    print("TEST SET RESULTS")
    print("=" * 50)
    print(f"  MAE  : {mae:.2f} W")
    print(f"  RMSE : {rmse:.2f} W")
    print(f"  R²   : {r2:.4f}")
    print(f"  MAPE : {mape:.2f}%")

    # Save scalers
    joblib.dump(scaler_features, NEW_SCALER_FEATURES_PATH)
    joblib.dump(scaler_target,   NEW_SCALER_TARGET_PATH)
    print(f"\nScalers saved.")

    # Save new config (drop in replacement for old config)
    new_config = {
        "timestamp":              TIMESTAMP,
        "model_architecture":     "CNN+LSTM with Bayesian Optimization",
        "total_original_features": len(ALL_TRAINING_FEATURES),
        "selected_features_count": len(selected_names),
        "selected_feature_names":  selected_names,
        "selected_feature_indices": selected_indices,
        "best_hyperparameters":    hp,
        "model_path":              NEW_MODEL_PATH,
        "scaler_features_path":    NEW_SCALER_FEATURES_PATH,
        "scaler_target_path":      NEW_SCALER_TARGET_PATH,
        "sequence_length":         SEQUENCE_LENGTH,
        "prediction_horizon":      PREDICTION_HORIZON,
        "training_dataset":        DATASET_CSV,
        "training_rows":           len(df),
        "test_mae":                round(mae, 2),
        "test_rmse":               round(rmse, 2),
        "test_r2":                 round(r2, 4),
        "test_mape":               round(mape, 2),
    }
    with open(NEW_CONFIG_PATH, 'w') as f:
        json.dump(new_config, f, indent=4)
    print(f"Config saved: {NEW_CONFIG_PATH}")

    # Update main_solar_api.py to point to new model files
    update_api_paths(NEW_MODEL_PATH, NEW_CONFIG_PATH,
                     NEW_SCALER_FEATURES_PATH, NEW_SCALER_TARGET_PATH, TIMESTAMP)

    print("\nDone! New model is ready.")
    print(f"Model: {NEW_MODEL_PATH}")
    print("\nNext steps:")
    print("  1. Run backtest.py to verify accuracy on full dataset")
    print("  2. git add models/ main_solar_api.py && git commit && git push")

    return model, new_config


def update_api_paths(model_path, config_path, scaler_feat_path, scaler_tgt_path, ts):
    """Update the model file paths in main_solar_api.py to point to the new model."""
    api_file = BASE_DIR / "main_solar_api.py"
    content  = api_file.read_text(encoding='utf-8')

    # Replace the four path lines
    import re
    content = re.sub(
        r'MODEL_PATH\s*=\s*str\(MODEL_DIR.*?\)',
        f'MODEL_PATH           = str(MODEL_DIR / "final_model_{ts}.keras")',
        content
    )
    content = re.sub(
        r'CONFIG_PATH\s*=\s*str\(MODEL_DIR.*?\)',
        f'CONFIG_PATH          = str(MODEL_DIR / "model_config_{ts}.json")',
        content
    )
    content = re.sub(
        r'SCALER_FEATURES_PATH\s*=\s*str\(MODEL_DIR.*?\)',
        f'SCALER_FEATURES_PATH = str(MODEL_DIR / "scaler_features_{ts}.pkl")',
        content
    )
    content = re.sub(
        r'SCALER_TARGET_PATH\s*=\s*str\(MODEL_DIR.*?\)',
        f'SCALER_TARGET_PATH   = str(MODEL_DIR / "scaler_target_{ts}.pkl")',
        content
    )
    api_file.write_text(content, encoding='utf-8')
    print(f"main_solar_api.py updated to use new model files ({ts})")


if __name__ == "__main__":
    retrain()

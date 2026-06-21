"""
Backtesting script for Solar Power Prediction Model
- Loads full 1-year dataset
- Slides a 48h window through the data
- At each step predicts next 24h, compares with actual values
- Outputs MAE, RMSE, R2, MAPE and saves detailed results to CSV
"""

import pandas as pd
import numpy as np
import joblib
import json
import os
import zipfile
import tempfile
from pathlib import Path
from datetime import timedelta
from tensorflow import keras

# ===========================
# PATHS
# ===========================
BASE_DIR = Path(__file__).parent

MODEL_DIR  = BASE_DIR / "models"
MODEL_PATH           = str(MODEL_DIR / "final_model_20250928_225759.keras")
CONFIG_PATH          = str(MODEL_DIR / "model_config_20250928_225800.json")
SCALER_FEATURES_PATH = str(MODEL_DIR / "scaler_features_20250928_225800.pkl")
SCALER_TARGET_PATH   = str(MODEL_DIR / "scaler_target_20250928_225800.pkl")

# Full 1-year dataset for backtesting
BACKTEST_CSV = r"F:\research papers\isuru\New folder (6)\hourly_solar_power_imputed original_new.csv"

# Point to the new retrained model files
MODEL_PATH           = str(MODEL_DIR / "final_model_20260621_192314.keras")
CONFIG_PATH          = str(MODEL_DIR / "model_config_20260621_192314.json")
SCALER_FEATURES_PATH = str(MODEL_DIR / "scaler_features_20260621_192314.pkl")
SCALER_TARGET_PATH   = str(MODEL_DIR / "scaler_target_20260621_192314.pkl")

LATITUDE  = 9.67
LONGITUDE = 80.18

SEQUENCE_LENGTH    = 48   # sliding window size (hours)
PREDICTION_HORIZON = 24   # predict next 24h
STEP_SIZE          = 1    # slide by 1 hour each step (set higher e.g. 24 to run faster)

OUTPUT_CSV     = str(BASE_DIR / "backtest_results.csv")
OUTPUT_SUMMARY = str(BASE_DIR / "backtest_summary.txt")

# ===========================
# ALL 62 TRAINING FEATURES
# ===========================
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
# LOAD MODEL
# ===========================
def load_legacy_keras_model(model_path):
    try:
        return keras.models.load_model(model_path, compile=False)
    except Exception as e:
        print(f"Direct load failed ({e}), patching config...")

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(model_path, 'r') as zf:
            zf.extractall(tmpdir)

        config_file = None
        for candidate in ('config.json', 'model.json'):
            p = os.path.join(tmpdir, candidate)
            if os.path.exists(p):
                config_file = p
                break

        with open(config_file, 'r') as f:
            model_config = json.load(f)

        def fix_config(obj):
            if isinstance(obj, dict):
                if 'batch_shape' in obj:
                    obj['batch_input_shape'] = obj.pop('batch_shape')
                if isinstance(obj.get('dtype'), dict):
                    dp = obj['dtype']
                    if dp.get('class_name') == 'DTypePolicy':
                        obj['dtype'] = dp.get('config', {}).get('name', 'float32')
                for v in list(obj.values()):
                    fix_config(v)
            elif isinstance(obj, list):
                for item in obj:
                    fix_config(item)

        fix_config(model_config)

        model = keras.models.model_from_json(json.dumps(model_config))

        weights_file = os.path.join(tmpdir, 'model.weights.h5')
        if os.path.exists(weights_file):
            _load_weights_by_name(model, weights_file)

        return model


def _load_weights_by_name(model, weights_path):
    import h5py
    with h5py.File(weights_path, 'r') as f:
        weight_map = {}

        def collect(name, obj):
            if not isinstance(obj, h5py.Dataset):
                return
            parts = name.split('/')
            if 'vars' in parts:
                vars_idx = parts.index('vars')
                layer_key = '/'.join(parts[:vars_idx])
                try:
                    var_idx = int(parts[vars_idx + 1])
                except (IndexError, ValueError):
                    return
                weight_map.setdefault(layer_key, {})[var_idx] = obj[()]

        f.visititems(collect)

        for layer in model.layers:
            lname = layer.name
            if lname not in weight_map:
                continue
            var_dict = weight_map[lname]
            weights = [var_dict[i] for i in sorted(var_dict.keys())]
            if len(weights) != len(layer.get_weights()):
                continue
            try:
                layer.set_weights(weights)
            except Exception:
                pass


# ===========================
# FEATURE ENGINEERING
# ===========================
def create_all_features(df):
    df = df.copy()

    if 'datetime' not in df.columns:
        if 'time' in df.columns:
            df['datetime'] = pd.to_datetime(df['time'])
        elif 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'])

    df['hour']        = df['datetime'].dt.hour
    df['day_of_year'] = df['datetime'].dt.dayofyear
    lat_rad = np.radians(LATITUDE)

    df['solar_declination'] = 23.45 * np.sin(np.radians(360 * (284 + df['day_of_year']) / 365))
    df['hour_angle']        = 15 * (df['hour'] - 12)

    sin_elevation = (
        np.sin(np.radians(df['solar_declination'])) * np.sin(lat_rad) +
        np.cos(np.radians(df['solar_declination'])) * np.cos(lat_rad) *
        np.cos(np.radians(df['hour_angle']))
    )
    df['solar_elevation_rad'] = np.arcsin(np.clip(sin_elevation, -1, 1))
    df['solar_elevation_deg'] = np.maximum(0, np.degrees(df['solar_elevation_rad']))

    cos_azimuth = (
        (np.sin(np.radians(df['solar_declination'])) * np.cos(lat_rad) -
         np.cos(np.radians(df['solar_declination'])) * np.sin(lat_rad) *
         np.cos(np.radians(df['hour_angle']))) /
        (np.cos(df['solar_elevation_rad']) + 1e-10)
    )
    df['solar_azimuth_rad'] = np.arccos(np.clip(cos_azimuth, -1, 1))
    df['solar_azimuth_deg'] = np.degrees(df['solar_azimuth_rad'])
    df.loc[df['hour'] > 12, 'solar_azimuth_deg'] = 360 - df.loc[df['hour'] > 12, 'solar_azimuth_deg']

    df['is_daylight']    = (df['solar_elevation_deg'] > 0).astype(int)
    df['solar_potential']= df['solar_elevation_deg'] / 90.0

    if 'relative_humidity_2m' in df.columns and 'relative_humidity_2m ' not in df.columns:
        df['relative_humidity_2m '] = df['relative_humidity_2m']
    if 'wind_speed_10m' in df.columns:
        df['wind_cooling'] = df['wind_speed_10m'] * 0.1

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
            df[f'Power(W)_roll_std_{window}h']   = df['Power(W)'].rolling(window, min_periods=1).std().fillna(0)
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


# ===========================
# SOLAR CONSTRAINT
# ===========================
def apply_solar_constraints(predictions, start_time):
    constrained = predictions.copy()
    lat_rad = np.radians(LATITUDE)
    for i in range(len(constrained)):
        ts = start_time + timedelta(hours=i + 1)
        hour = ts.hour
        doy  = ts.timetuple().tm_yday
        decl = 23.45 * np.sin(np.radians(360 * (284 + doy) / 365))
        ha   = 15 * (hour - 12)
        sin_elev = (np.sin(np.radians(decl)) * np.sin(lat_rad) +
                    np.cos(np.radians(decl)) * np.cos(lat_rad) *
                    np.cos(np.radians(ha)))
        elev = np.degrees(np.arcsin(np.clip(sin_elev, -1, 1)))
        if elev <= 0:
            constrained[i] = 0.0
        elif elev < 5:
            constrained[i] *= (elev / 5) * 0.1
    return constrained


# ===========================
# SINGLE PREDICTION
# ===========================
def predict_from_window(window_df, model, scaler_features, scaler_target, selected_indices):
    X_all = np.zeros((len(window_df), len(ALL_TRAINING_FEATURES)))
    for i, feat in enumerate(ALL_TRAINING_FEATURES):
        if feat in window_df.columns:
            X_all[:, i] = window_df[feat].values

    X_scaled   = scaler_features.transform(X_all)
    X_selected = X_scaled[:, selected_indices]
    X_seq      = X_selected[-SEQUENCE_LENGTH:].reshape(1, SEQUENCE_LENGTH, len(selected_indices))

    pred_scaled  = model.predict(X_seq, verbose=0)
    predictions  = scaler_target.inverse_transform(pred_scaled.reshape(-1, 1)).flatten()
    predictions  = np.maximum(0, predictions)
    predictions  = apply_solar_constraints(predictions, window_df['datetime'].max())
    return predictions


# ===========================
# METRICS
# ===========================
def compute_metrics(actual, predicted):
    actual    = np.array(actual)
    predicted = np.array(predicted)

    # Overall metrics (all hours)
    mae  = np.mean(np.abs(actual - predicted))
    rmse = np.sqrt(np.mean((actual - predicted) ** 2))
    ss_res = np.sum((actual - predicted) ** 2)
    ss_tot = np.sum((actual - np.mean(actual)) ** 2)
    r2   = 1 - ss_res / ss_tot if ss_tot > 0 else float('nan')

    # Daytime-only metrics (actual > 100W) — excludes night zeros and near-zero transition
    day_mask = actual > 100
    if day_mask.sum() > 0:
        day_actual    = actual[day_mask]
        day_predicted = predicted[day_mask]
        mae_day  = np.mean(np.abs(day_actual - day_predicted))
        rmse_day = np.sqrt(np.mean((day_actual - day_predicted) ** 2))
        mape_day = np.mean(np.abs((day_actual - day_predicted) / day_actual)) * 100
        ss_res_d = np.sum((day_actual - day_predicted) ** 2)
        ss_tot_d = np.sum((day_actual - np.mean(day_actual)) ** 2)
        r2_day   = 1 - ss_res_d / ss_tot_d if ss_tot_d > 0 else float('nan')
    else:
        mae_day = rmse_day = mape_day = r2_day = float('nan')

    return {
        "MAE": mae, "RMSE": rmse, "R2": r2,
        "MAE_day": mae_day, "RMSE_day": rmse_day,
        "R2_day": r2_day, "MAPE_day": mape_day
    }


# ===========================
# MAIN BACKTEST
# ===========================
def run_backtest():
    print("=" * 60)
    print("SOLAR PREDICTION BACKTESTING")
    print("=" * 60)

    # Load dataset
    print(f"\nLoading dataset: {BACKTEST_CSV}")
    df = pd.read_csv(BACKTEST_CSV)
    if 'time' in df.columns:
        df['datetime'] = pd.to_datetime(df['time'])
    elif 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('datetime').reset_index(drop=True)
    print(f"Dataset: {len(df)} rows | {df['datetime'].min()} → {df['datetime'].max()}")

    # Build full feature set once on the entire dataset
    print("\nEngineering features for full dataset...")
    df_feat = create_all_features(df)
    print("Done.")

    # Load model and scalers
    print("\nLoading model and scalers...")
    model           = load_legacy_keras_model(MODEL_PATH)
    model.compile(optimizer='adam', loss='mse')
    scaler_features = joblib.load(SCALER_FEATURES_PATH)
    scaler_target   = joblib.load(SCALER_TARGET_PATH)

    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    selected_indices = config['selected_feature_indices']
    print("Model loaded.")

    # How many steps can we run?
    # Need SEQUENCE_LENGTH rows for input + PREDICTION_HORIZON rows for actual comparison
    max_start = len(df_feat) - SEQUENCE_LENGTH - PREDICTION_HORIZON
    steps     = range(0, max_start, STEP_SIZE)
    total     = len(steps)

    print(f"\nBacktest steps: {total} (step size = {STEP_SIZE}h)")
    print(f"Each step: use rows [i : i+{SEQUENCE_LENGTH}] → predict next {PREDICTION_HORIZON}h\n")

    results = []
    all_actual    = []
    all_predicted = []

    for step_num, i in enumerate(steps):
        window_df  = df_feat.iloc[i : i + SEQUENCE_LENGTH].copy()
        actual_df  = df_feat.iloc[i + SEQUENCE_LENGTH : i + SEQUENCE_LENGTH + PREDICTION_HORIZON]

        if len(actual_df) < PREDICTION_HORIZON:
            break

        actual_values = actual_df['Power(W)'].values

        try:
            predicted_values = predict_from_window(
                window_df, model, scaler_features, scaler_target, selected_indices
            )
        except Exception as e:
            print(f"Step {step_num}: prediction failed — {e}")
            continue

        # Trim to same length
        n = min(len(actual_values), len(predicted_values))
        actual_values    = actual_values[:n]
        predicted_values = predicted_values[:n]

        all_actual.extend(actual_values)
        all_predicted.extend(predicted_values)

        # Save per-hour results
        window_end_time = window_df['datetime'].max()
        for h in range(n):
            results.append({
                'window_end':  window_end_time,
                'predict_hour': h + 1,
                'timestamp':   actual_df['datetime'].iloc[h],
                'actual_W':    actual_values[h],
                'predicted_W': predicted_values[h],
                'error_W':     predicted_values[h] - actual_values[h],
                'abs_error_W': abs(predicted_values[h] - actual_values[h]),
            })

        # Progress update every 100 steps
        if (step_num + 1) % 100 == 0 or step_num == 0:
            metrics = compute_metrics(all_actual, all_predicted)
            print(f"Step {step_num+1}/{total} | "
                  f"MAE={metrics['MAE']:.1f}W | "
                  f"R²={metrics['R2']:.4f} | "
                  f"[Daytime] MAE={metrics['MAE_day']:.1f}W | "
                  f"R²={metrics['R2_day']:.4f} | "
                  f"MAPE={metrics['MAPE_day']:.2f}%")

    # Final metrics
    print("\n" + "=" * 60)
    print("FINAL BACKTEST RESULTS")
    print("=" * 60)
    final = compute_metrics(all_actual, all_predicted)
    print(f"  --- All hours ---")
    print(f"  MAE  : {final['MAE']:.2f} W")
    print(f"  RMSE : {final['RMSE']:.2f} W")
    print(f"  R²   : {final['R2']:.4f}")
    print(f"\n  --- Daytime only (actual > 100W) ---")
    print(f"  MAE  : {final['MAE_day']:.2f} W")
    print(f"  RMSE : {final['RMSE_day']:.2f} W")
    print(f"  R²   : {final['R2_day']:.4f}")
    print(f"  MAPE : {final['MAPE_day']:.2f}%")
    print(f"\n  Total predictions: {len(all_actual)}")

    # Per-hour-ahead accuracy
    results_df = pd.DataFrame(results)
    print("\nPer-hour-ahead MAE:")
    for h in range(1, PREDICTION_HORIZON + 1):
        h_df = results_df[results_df['predict_hour'] == h]
        if len(h_df):
            print(f"  H+{h:02d}: MAE={h_df['abs_error_W'].mean():.1f}W")

    # Save results
    results_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nDetailed results saved to: {OUTPUT_CSV}")

    # Save summary
    with open(OUTPUT_SUMMARY, 'w', encoding='utf-8') as f:
        f.write("BACKTEST SUMMARY\n")
        f.write("=" * 40 + "\n")
        f.write(f"Dataset: {BACKTEST_CSV}\n")
        f.write(f"Total rows: {len(df)}\n")
        f.write(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}\n")
        f.write(f"Steps run: {total}\n")
        f.write(f"Step size: {STEP_SIZE}h\n\n")
        f.write(f"--- All hours ---\n")
        f.write(f"MAE  : {final['MAE']:.2f} W\n")
        f.write(f"RMSE : {final['RMSE']:.2f} W\n")
        f.write(f"R2   : {final['R2']:.4f}\n\n")
        f.write(f"--- Daytime only (actual > 100W) ---\n")
        f.write(f"MAE  : {final['MAE_day']:.2f} W\n")
        f.write(f"RMSE : {final['RMSE_day']:.2f} W\n")
        f.write(f"R2   : {final['R2_day']:.4f}\n")
        f.write(f"MAPE : {final['MAPE_day']:.2f}%\n")
    print(f"Summary saved to: {OUTPUT_SUMMARY}")

    return results_df, final


if __name__ == "__main__":
    results_df, metrics = run_backtest()

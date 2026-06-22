"""
Bayesian Hyperparameter Search for CNN+LSTM Solar Prediction Model
Uses Optuna (TPE sampler) to find optimal architecture on the full 1-year dataset.

Run: python hyperparameter_search.py
After completion: python retrain.py   (uses the best hyperparameters found)
"""

import pandas as pd
import numpy as np
import json
import joblib
import os
import warnings
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from pathlib import Path
from datetime import datetime
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, regularizers
from sklearn.preprocessing import StandardScaler, MaxAbsScaler
from sklearn.metrics import mean_absolute_error, r2_score

tf.get_logger().setLevel('ERROR')

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    print("Installing optuna...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "optuna", "-q"])
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

# ===========================
# PATHS
# ===========================
BASE_DIR  = Path(__file__).parent
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

DATASET_CSV = r"F:\research papers\isuru\New folder (6)\hourly_solar_power_imputed original_new.csv"

TIMESTAMP          = datetime.now().strftime("%Y%m%d_%H%M%S")
BEST_CONFIG_PATH   = str(MODEL_DIR / f"model_config_{TIMESTAMP}.json")
BEST_MODEL_PATH    = str(MODEL_DIR / f"final_model_{TIMESTAMP}.keras")
BEST_SCALER_F_PATH = str(MODEL_DIR / f"scaler_features_{TIMESTAMP}.pkl")
BEST_SCALER_T_PATH = str(MODEL_DIR / f"scaler_target_{TIMESTAMP}.pkl")

LATITUDE  = 9.67
LONGITUDE = 80.18

SEQUENCE_LENGTH    = 48
PREDICTION_HORIZON = 24
N_TRIALS           = 40   # number of hyperparameter combinations to try
EPOCHS_PER_TRIAL   = 30   # fast trial: early stop at patience=5
FINAL_EPOCHS       = 150  # full retrain of best config

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


def build_sequences(X, y, seq_len, horizon):
    Xs, ys = [], []
    for i in range(len(X) - seq_len - horizon + 1):
        Xs.append(X[i : i + seq_len])
        ys.append(y[i + seq_len : i + seq_len + horizon])
    return np.array(Xs), np.array(ys)


def build_model_from_hp(trial_hp, n_features, seq_len, horizon):
    """Build CNN+LSTM model from Optuna trial hyperparameters."""
    l2_reg  = regularizers.l2(trial_hp['l2_regularization'])
    inputs  = keras.Input(shape=(seq_len, n_features))
    x       = inputs

    # CNN block 1
    for _ in range(trial_hp['n_conv_layers_block1']):
        x = layers.Conv1D(trial_hp['conv_filters_1'], trial_hp['kernel_size_1'],
                          activation='relu', padding='same', kernel_regularizer=l2_reg)(x)
    x = layers.MaxPooling1D(pool_size=min(trial_hp['pool_size_1'], x.shape[1]))(x)
    x = layers.Dropout(trial_hp['dropout_conv_1'])(x)

    # CNN block 2 (optional)
    if trial_hp.get('use_second_cnn', False):
        for _ in range(trial_hp['n_conv_layers_block2']):
            x = layers.Conv1D(trial_hp['conv_filters_2'], trial_hp['kernel_size_2'],
                              activation='relu', padding='same', kernel_regularizer=l2_reg)(x)
        x = layers.MaxPooling1D(pool_size=min(trial_hp['pool_size_2'], x.shape[1]))(x)
        x = layers.Dropout(trial_hp['dropout_conv_2'])(x)

    # LSTM
    x = layers.LSTM(trial_hp['lstm_units'],
                    dropout=trial_hp['dropout_lstm'],
                    recurrent_dropout=trial_hp['recurrent_dropout'])(x)
    x = layers.Dropout(trial_hp['dropout_after_lstm'])(x)

    # Dense layers
    for i in range(trial_hp['n_dense_layers']):
        x = layers.Dense(trial_hp[f'dense_units_{i}'], activation='relu')(x)
        x = layers.Dropout(trial_hp[f'dropout_dense_{i}'])(x)

    outputs = layers.Dense(horizon)(x)
    model   = keras.Model(inputs, outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=trial_hp['learning_rate']),
        loss='mse',
        metrics=['mae']
    )
    return model


# ===========================
# LOAD & PREPARE DATA (once)
# ===========================
print("=" * 60)
print("BAYESIAN HYPERPARAMETER SEARCH — CNN+LSTM SOLAR MODEL")
print("=" * 60)

print("\nLoading and preparing data...")
df_raw = pd.read_csv(DATASET_CSV)
df_raw['datetime'] = pd.to_datetime(df_raw['time'])
df_raw = df_raw.sort_values('datetime').reset_index(drop=True)
print(f"  Rows: {len(df_raw)} | {df_raw['datetime'].min().date()} to {df_raw['datetime'].max().date()}")

df_feat = create_all_features(df_raw)

X_all = np.zeros((len(df_feat), len(ALL_TRAINING_FEATURES)))
for i, feat in enumerate(ALL_TRAINING_FEATURES):
    if feat in df_feat.columns:
        X_all[:, i] = df_feat[feat].values
y_all = df_feat['Power(W)'].values

# Drop warm-up rows
X_all = X_all[SEQUENCE_LENGTH:]
y_all = y_all[SEQUENCE_LENGTH:]

# Fit scalers on full data
scaler_features = StandardScaler()
scaler_target   = MaxAbsScaler()
X_scaled = scaler_features.fit_transform(X_all)
y_scaled = scaler_target.fit_transform(y_all.reshape(-1, 1)).flatten()

# Use all 32 features (let search find best architecture, not feature subset)
selected_indices = list(range(len(ALL_TRAINING_FEATURES)))
X_sel = X_scaled
n_features = X_sel.shape[1]

# Build sequences
X_seq, y_seq = build_sequences(X_sel, y_scaled, SEQUENCE_LENGTH, PREDICTION_HORIZON)
print(f"  Sequences: {X_seq.shape}")

# 70/15/15 split for search (more val data = better signal)
n       = len(X_seq)
n_train = int(n * 0.70)
n_val   = int(n * 0.15)

X_train = X_seq[:n_train]
y_train = y_seq[:n_train]
X_val   = X_seq[n_train:n_train + n_val]
y_val   = y_seq[n_train:n_train + n_val]
X_test  = X_seq[n_train + n_val:]
y_test  = y_seq[n_train + n_val:]

print(f"  Train: {len(X_train)} | Val: {len(X_val)} | Test: {len(X_test)}")


# ===========================
# OPTUNA OBJECTIVE
# ===========================
def objective(trial):
    hp = {
        # CNN block 1
        'n_conv_layers_block1': trial.suggest_int('n_conv_layers_block1', 1, 3),
        'conv_filters_1':       trial.suggest_categorical('conv_filters_1', [32, 64, 128]),
        'kernel_size_1':        trial.suggest_categorical('kernel_size_1', [3, 5, 7]),
        'l2_regularization':    trial.suggest_float('l2_reg', 1e-6, 1e-3, log=True),
        'pool_size_1':          trial.suggest_categorical('pool_size_1', [2, 3]),
        'dropout_conv_1':       trial.suggest_float('dropout_conv_1', 0.1, 0.5),
        # CNN block 2
        'use_second_cnn':       trial.suggest_categorical('use_second_cnn', [True, False]),
        'n_conv_layers_block2': trial.suggest_int('n_conv_layers_block2', 1, 2),
        'conv_filters_2':       trial.suggest_categorical('conv_filters_2', [32, 64, 128]),
        'kernel_size_2':        trial.suggest_categorical('kernel_size_2', [3, 5, 7]),
        'pool_size_2':          trial.suggest_categorical('pool_size_2', [2, 3]),
        'dropout_conv_2':       trial.suggest_float('dropout_conv_2', 0.1, 0.5),
        # LSTM
        'lstm_units':           trial.suggest_categorical('lstm_units', [64, 96, 128, 192, 256]),
        'dropout_lstm':         trial.suggest_float('dropout_lstm', 0.1, 0.5),
        'recurrent_dropout':    trial.suggest_float('recurrent_dropout', 0.0, 0.4),
        'dropout_after_lstm':   trial.suggest_float('dropout_after_lstm', 0.2, 0.6),
        # Dense
        'n_dense_layers':       trial.suggest_int('n_dense_layers', 1, 2),
        'dense_units_0':        trial.suggest_categorical('dense_units_0', [32, 64, 128]),
        'dropout_dense_0':      trial.suggest_float('dropout_dense_0', 0.1, 0.4),
        'dense_units_1':        trial.suggest_categorical('dense_units_1', [32, 64]),
        'dropout_dense_1':      trial.suggest_float('dropout_dense_1', 0.1, 0.4),
        # Optimizer
        'learning_rate':        trial.suggest_float('lr', 5e-4, 1e-2, log=True),
    }

    try:
        keras.backend.clear_session()
        model = build_model_from_hp(hp, n_features, SEQUENCE_LENGTH, PREDICTION_HORIZON)

        callbacks = [
            keras.callbacks.EarlyStopping(patience=5, restore_best_weights=True,
                                          monitor='val_loss'),
            keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=3,
                                              monitor='val_loss'),
        ]
        model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=EPOCHS_PER_TRIAL,
            batch_size=64,
            callbacks=callbacks,
            verbose=0
        )

        val_pred = model.predict(X_val, verbose=0)
        val_pred_inv = scaler_target.inverse_transform(val_pred.reshape(-1,1)).flatten()
        val_true_inv = scaler_target.inverse_transform(y_val.reshape(-1,1)).flatten()
        val_pred_inv = np.maximum(0, val_pred_inv)

        mae = mean_absolute_error(val_true_inv, val_pred_inv)
        return mae

    except Exception as e:
        print(f"  Trial failed: {e}")
        return float('inf')


# ===========================
# RUN SEARCH
# ===========================
print(f"\nStarting Optuna search: {N_TRIALS} trials × {EPOCHS_PER_TRIAL} epochs each...")
print("(This takes ~30-60 minutes on CPU)\n")

study = optuna.create_study(
    direction='minimize',
    sampler=optuna.samplers.TPESampler(seed=42),
    pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=10)
)
study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=True)

best_trial = study.best_trial
print(f"\n{'='*60}")
print(f"BEST TRIAL: #{best_trial.number}  Val MAE = {best_trial.value:.2f} W")
print(f"{'='*60}")

# Reconstruct best HP dict matching retrain.py format
bp = best_trial.params
best_hp = {
    'n_conv_layers_block1': bp['n_conv_layers_block1'],
    'conv_filters_1':       bp['conv_filters_1'],
    'kernel_size_1':        bp['kernel_size_1'],
    'l2_regularization':    bp['l2_reg'],
    'pool_size_1':          bp['pool_size_1'],
    'dropout_conv_1':       bp['dropout_conv_1'],
    'use_second_cnn':       bp['use_second_cnn'],
    'n_conv_layers_block2': bp['n_conv_layers_block2'],
    'conv_filters_2':       bp['conv_filters_2'],
    'kernel_size_2':        bp['kernel_size_2'],
    'pool_size_2':          bp['pool_size_2'],
    'dropout_conv_2':       bp['dropout_conv_2'],
    'lstm_units':           bp['lstm_units'],
    'dropout_lstm':         bp['dropout_lstm'],
    'recurrent_dropout':    bp['recurrent_dropout'],
    'dropout_after_lstm':   bp['dropout_after_lstm'],
    'n_dense_layers':       bp['n_dense_layers'],
    'dense_units_0':        bp['dense_units_0'],
    'dropout_dense_0':      bp['dropout_dense_0'],
    'dense_units_1':        bp.get('dense_units_1', 64),
    'dropout_dense_1':      bp.get('dropout_dense_1', 0.2),
    'learning_rate':        bp['lr'],
}

print("\nBest hyperparameters:")
for k, v in best_hp.items():
    print(f"  {k}: {v}")


# ===========================
# FINAL FULL RETRAIN with best HP
# ===========================
print(f"\n{'='*60}")
print(f"FINAL RETRAIN with best HP — {FINAL_EPOCHS} epochs")
print(f"{'='*60}")

keras.backend.clear_session()
model = build_model_from_hp(best_hp, n_features, SEQUENCE_LENGTH, PREDICTION_HORIZON)
model.summary()

callbacks = [
    keras.callbacks.EarlyStopping(patience=15, restore_best_weights=True,
                                  monitor='val_loss', verbose=1),
    keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=7,
                                      monitor='val_loss', verbose=1),
    keras.callbacks.ModelCheckpoint(BEST_MODEL_PATH, save_best_only=True,
                                    monitor='val_loss', verbose=1),
]

history = model.fit(
    X_train, y_train,
    validation_data=(X_val, y_val),
    epochs=FINAL_EPOCHS,
    batch_size=32,
    callbacks=callbacks,
    verbose=1
)

# Evaluate on test set
print("\nEvaluating on test set...")
y_pred_scaled = model.predict(X_test, verbose=0)
y_test_inv = scaler_target.inverse_transform(y_test.reshape(-1,1)).reshape(y_test.shape)
y_pred_inv = scaler_target.inverse_transform(y_pred_scaled.reshape(-1,1)).reshape(y_pred_scaled.shape)
y_test_flat = y_test_inv.flatten()
y_pred_flat = np.maximum(0, y_pred_inv.flatten())

mae  = mean_absolute_error(y_test_flat, y_pred_flat)
rmse = np.sqrt(np.mean((y_test_flat - y_pred_flat)**2))
r2   = r2_score(y_test_flat, y_pred_flat)
mask = y_test_flat > 100
mape = np.mean(np.abs((y_test_flat[mask] - y_pred_flat[mask]) / y_test_flat[mask])) * 100

print(f"\n{'='*50}")
print("FINAL TEST RESULTS")
print(f"{'='*50}")
print(f"  MAE  (all hours) : {mae:.2f} W")
print(f"  RMSE (all hours) : {rmse:.2f} W")
print(f"  R²               : {r2:.4f}")
print(f"  MAPE (daytime)   : {mape:.2f}%")

# Save scalers
joblib.dump(scaler_features, BEST_SCALER_F_PATH)
joblib.dump(scaler_target,   BEST_SCALER_T_PATH)

# Save config — same format as model_config used by main_solar_api.py
new_config = {
    "timestamp":                TIMESTAMP,
    "model_architecture":       "CNN+LSTM with Optuna Bayesian Search",
    "total_original_features":  len(ALL_TRAINING_FEATURES),
    "selected_features_count":  len(ALL_TRAINING_FEATURES),
    "selected_feature_names":   ALL_TRAINING_FEATURES,
    "selected_feature_indices": selected_indices,
    "best_hyperparameters":     best_hp,
    "model_path":               BEST_MODEL_PATH,
    "scaler_features_path":     BEST_SCALER_F_PATH,
    "scaler_target_path":       BEST_SCALER_T_PATH,
    "sequence_length":          SEQUENCE_LENGTH,
    "prediction_horizon":       PREDICTION_HORIZON,
    "search_results": {
        "n_trials":    N_TRIALS,
        "best_val_mae": best_trial.value,
        "test_mae":    mae,
        "test_rmse":   rmse,
        "test_r2":     r2,
        "test_mape_daytime": mape,
    }
}
with open(BEST_CONFIG_PATH, 'w') as f:
    json.dump(new_config, f, indent=4)

print(f"\nSaved:")
print(f"  Model  : {BEST_MODEL_PATH}")
print(f"  Config : {BEST_CONFIG_PATH}")
print(f"  Scalers: {BEST_SCALER_F_PATH}")
print(f"          {BEST_SCALER_T_PATH}")

# Auto-update main_solar_api.py paths
api_file = BASE_DIR / "main_solar_api.py"
content  = api_file.read_text(encoding='utf-8')
import re
content = re.sub(r'final_model_\d+_\d+\.keras',   Path(BEST_MODEL_PATH).name,   content)
content = re.sub(r'model_config_\d+_\d+\.json',   Path(BEST_CONFIG_PATH).name,  content)
content = re.sub(r'scaler_features_\d+_\d+\.pkl', Path(BEST_SCALER_F_PATH).name, content)
content = re.sub(r'scaler_target_\d+_\d+\.pkl',   Path(BEST_SCALER_T_PATH).name, content)
api_file.write_text(content, encoding='utf-8')
print(f"\nUpdated main_solar_api.py to use new model files.")

print(f"\n{'='*60}")
print("DONE! Next steps:")
print("  1. Run backtest.py to measure accuracy on full 1-year dataset")
print("  2. git add models/ main_solar_api.py backtest_results.csv")
print("  3. git push → Railway auto-deploys")
print(f"{'='*60}")

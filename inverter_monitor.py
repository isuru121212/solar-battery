"""
Live inverter monitoring — fully decoupled from the solar prediction/optimization
pipeline. Subscribes to inverter readings published over MQTT (EMQX broker) by the
laptop that's connected to the inverter via Modbus, and exposes them over REST so
the dashboard can show a live "Monitor" tab.

Wiring: main_solar_api.py calls start_inverter_monitor() at startup and
app.include_router(inverter_router) — no other file needs to change.
"""
import json
import logging
import os
import threading
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter

logger = logging.getLogger("inverter_monitor")

# ── Configuration (env vars, set on Railway) ──────────────────────────────
MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "8883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_USE_TLS = os.environ.get("MQTT_USE_TLS", "true").lower() == "true"
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "solar/inverter/readings")
MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "cloud-inverter-subscriber")

HISTORY_MAXLEN = 500  # ~8 hours at 1 reading/minute

# ── In-memory state ────────────────────────────────────────────────────────
_latest_reading: dict | None = None
_history: deque = deque(maxlen=HISTORY_MAXLEN)
_lock = threading.Lock()
_connected = False


def _on_connect(client, userdata, flags, rc, properties=None):
    global _connected
    _connected = rc == 0
    if _connected:
        logger.info(f"Inverter monitor: connected to MQTT broker, subscribing to '{MQTT_TOPIC}'")
        client.subscribe(MQTT_TOPIC, qos=1)
    else:
        logger.error(f"Inverter monitor: MQTT connect failed (rc={rc})")


def _on_disconnect(client, userdata, rc, properties=None):
    global _connected
    _connected = False
    logger.warning(f"Inverter monitor: MQTT disconnected (rc={rc})")


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(f"Inverter monitor: dropped unparseable message: {e}")
        return

    payload.setdefault("received_at", datetime.now(timezone.utc).isoformat())

    with _lock:
        global _latest_reading
        _latest_reading = payload
        _history.append(payload)


def start_inverter_monitor():
    """Start the MQTT subscriber in a background thread. Safe no-op if unconfigured."""
    if not MQTT_BROKER_HOST:
        logger.warning("Inverter monitor: MQTT_BROKER_HOST not set — live monitoring disabled")
        return

    import paho.mqtt.client as mqtt

    client = mqtt.Client(client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_USE_TLS:
        client.tls_set()

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message

    def _run():
        while True:
            try:
                client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
                client.loop_forever(retry_first_connection=True)
            except Exception as e:
                logger.error(f"Inverter monitor: MQTT loop error: {e} — retrying in 5s")
                import time
                time.sleep(5)

    thread = threading.Thread(target=_run, name="inverter-mqtt", daemon=True)
    thread.start()
    logger.info("Inverter monitor: background MQTT thread started")


# ── REST routes ─────────────────────────────────────────────────────────
inverter_router = APIRouter(prefix="/inverter", tags=["inverter"])


@inverter_router.get("/status")
def inverter_status():
    return {
        "configured": bool(MQTT_BROKER_HOST),
        "connected": _connected,
        "topic": MQTT_TOPIC,
        "readings_buffered": len(_history),
    }


@inverter_router.get("/latest")
def inverter_latest():
    with _lock:
        return _latest_reading or {}


@inverter_router.get("/history")
def inverter_history(limit: int = 100):
    with _lock:
        items = list(_history)[-limit:]
    return {"count": len(items), "readings": items}

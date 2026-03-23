#!/usr/bin/env python3
"""
Pi 1 — Living Room
Role : Central server + MQTT broker host + living room sensors
Sensors : PIR (GPIO 24), DHT22 (GPIO 23), IR TX (GPIO 18), IR RX (GPIO 17),
          RGB LED (GPIO 27/22/12), Lamp relay (GPIO 6), Fan relay (GPIO 13)
"""

import json
import os
import sys
import threading
import time
from datetime import datetime

import adafruit_dht
import board
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO
from flask import Flask, jsonify, request
from flask_cors import CORS

# Shared config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    DHT_READ_INTERVAL, FLASK_PORT, MANUAL_OVERRIDE_SEC, MQTT_BROKER_IP,
    MQTT_PORT, NIGHT_END_HOUR, NIGHT_END_MIN, NIGHT_START_HOUR,
    NIGHT_START_MIN, PIR_TIMEOUT_SEC, SENSOR_PUBLISH_INTERVAL,
    TEMP_AC_THRESHOLD, TEMP_FAN_THRESHOLD, TOPICS, ULTRASONIC_PRESENCE_CM,
)

# ── Runtime config (mutable per-room, updated via /api/config) ────────────────

config_lock = threading.Lock()

_night = f"{NIGHT_START_HOUR:02d}:{NIGHT_START_MIN:02d}"
_dawn  = f"{NIGHT_END_HOUR:02d}:{NIGHT_END_MIN:02d}"

ROOM_CONFIGS = {
    "living-room": {
        "temp_fan_threshold":  TEMP_FAN_THRESHOLD,
        "temp_ac_threshold":   TEMP_AC_THRESHOLD,
        "pir_timeout_sec":     PIR_TIMEOUT_SEC,
        "manual_override_sec": MANUAL_OVERRIDE_SEC,
        "night_start":         _night,
        "night_end":           _dawn,
    },
    "bedroom": {
        "temp_ac_threshold":   TEMP_AC_THRESHOLD,
        "pir_timeout_sec":     PIR_TIMEOUT_SEC,
        "manual_override_sec": MANUAL_OVERRIDE_SEC,
        "night_start":         _night,
        "night_end":           _dawn,
    },
    "kitchen": {
        "pir_timeout_sec": PIR_TIMEOUT_SEC,
    },
}

# Convenience accessor for living-room config (used in this file's loops)
def lr_cfg(key):
    with config_lock:
        return ROOM_CONFIGS["living-room"][key]

# ── GPIO ──────────────────────────────────────────────────────────────────────

PIR_PIN   = 24
DHT_PIN   = 23
IR_TX_PIN = 18
IR_RX_PIN = 17
LAMP_PIN  = 6
FAN_PIN   = 13
RGB_RED   = 27
RGB_GREEN = 22
RGB_BLUE  = 12

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(PIR_PIN,   GPIO.IN)
GPIO.setup(LAMP_PIN,  GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(FAN_PIN,   GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(RGB_RED,   GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(RGB_GREEN, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(RGB_BLUE,  GPIO.OUT, initial=GPIO.LOW)

# PWM for RGB LED (100Hz)
_pwm_r = GPIO.PWM(RGB_RED,   100)
_pwm_g = GPIO.PWM(RGB_GREEN, 100)
_pwm_b = GPIO.PWM(RGB_BLUE,  100)
_pwm_r.start(0)
_pwm_g.start(0)
_pwm_b.start(0)

def set_rgb(r: int, g: int, b: int):
    """Set RGB LED color. Values 0-100 (duty cycle %)."""
    _pwm_r.ChangeDutyCycle(r)
    _pwm_g.ChangeDutyCycle(g)
    _pwm_b.ChangeDutyCycle(b)

def update_energy_led():
    """
    Update RGB LED based on energy wastage across all rooms.
    Blue  = away mode
    Green = no wastage (all rooms occupied or no appliances on)
    Yellow/Orange/Red = appliances on in empty rooms (more = redder)
    """
    with state_lock:
        away = STATE["away_mode"]
        lr_occupied  = STATE["living_room"]["occupied"]
        lr_appliances = STATE["living_room"]["appliances"]
        bed_occupied  = STATE["bedroom"]["occupied"]
        bed_appliances = STATE["bedroom"]["appliances"]
        kit_occupied  = STATE["kitchen"]["occupied"]

    if away:
        set_rgb(0, 0, 100)   # Blue
        return

    wasted = 0
    if not lr_occupied:
        wasted += sum(1 for v in lr_appliances.values() if v)
    if not bed_occupied:
        wasted += sum(1 for v in bed_appliances.values() if v)
    # Kitchen lamp auto-follows presence so not counted

    # Green → Yellow → Orange → Red based on wasted count (max ~6)
    ratio = min(wasted / 4.0, 1.0)   # normalise to 0-1
    r = int(ratio * 100)
    g = int((1 - ratio) * 100)
    set_rgb(r, g, 0)

# ── Shared state ──────────────────────────────────────────────────────────────

state_lock = threading.Lock()

STATE = {
    "living_room": {
        "occupied":    False,
        "last_motion": 0,
        "temp":        None,
        "humidity":    None,
        "appliances":  {"tv": False, "ac": False, "fan": False, "lamp": False},
        "overrides":   {},          # appliance_id -> expiry timestamp
    },
    "bedroom": {
        "occupied": False,
        "temp":     None,
        "humidity": None,
        "appliances": {"ac": False, "lamp": False},
    },
    "kitchen": {
        "occupied": False,
        "appliances": {"lamp": False},
    },
    "away_mode": False,
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_nighttime() -> bool:
    now = datetime.now()
    current = now.hour * 60 + now.minute
    sh, sm = map(int, lr_cfg("night_start").split(":"))
    eh, em = map(int, lr_cfg("night_end").split(":"))
    start = sh * 60 + sm
    end   = eh * 60 + em
    return current >= start or current < end

def _apply_gpio(appliance_id: str, on: bool):
    """Drive hardware for appliances that have a direct GPIO relay."""
    if appliance_id == "lamp":
        GPIO.output(LAMP_PIN, GPIO.HIGH if on else GPIO.LOW)
    elif appliance_id == "fan":
        GPIO.output(FAN_PIN, GPIO.HIGH if on else GPIO.LOW)

def set_appliance(appliance_id: str, on: bool, manual: bool = False) -> bool:
    """
    Update appliance state and drive GPIO. Returns True if IR should be sent.
    Must be called while state_lock is held. IR sending must happen outside the lock.
    """
    STATE["living_room"]["appliances"][appliance_id] = on
    if manual:
        STATE["living_room"]["overrides"][appliance_id] = time.time() + lr_cfg("manual_override_sec")
    else:
        # automation — clear any expired override (don't clear a live one)
        exp = STATE["living_room"]["overrides"].get(appliance_id, 0)
        if time.time() < exp:
            # still within manual override window — do not apply automation
            return False
    _apply_gpio(appliance_id, on)
    return appliance_id in ("tv", "ac", "fan")

# ── PIR loop ──────────────────────────────────────────────────────────────────

def pir_loop():
    """Poll PIR every 0.5 s; mark room empty after PIR_TIMEOUT_SEC of no motion."""
    while True:
        motion = GPIO.input(PIR_PIN)
        with state_lock:
            if motion:
                STATE["living_room"]["last_motion"] = time.time()
                STATE["living_room"]["occupied"]    = True
            else:
                elapsed = time.time() - STATE["living_room"]["last_motion"]
                if elapsed > lr_cfg("pir_timeout_sec"):
                    STATE["living_room"]["occupied"] = False
            occupied  = STATE["living_room"]["occupied"]
            away_mode = STATE["away_mode"]

        time.sleep(0.5)

# ── DHT22 loop ────────────────────────────────────────────────────────────────

def dht_loop():
    """Read DHT22 every DHT_READ_INTERVAL seconds."""
    dht_device = adafruit_dht.DHT22(board.D23)
    while True:
        try:
            temp     = dht_device.temperature
            humidity = dht_device.humidity
            if temp is not None and humidity is not None:
                with state_lock:
                    STATE["living_room"]["temp"]     = round(temp, 1)
                    STATE["living_room"]["humidity"] = round(humidity, 1)
                print(f"[DHT22] {temp:.1f}°C  {humidity:.1f}%")
        except RuntimeError as e:
            print("[DHT] Retry:", e)
        time.sleep(DHT_READ_INTERVAL)

# ── Automation loop ───────────────────────────────────────────────────────────

def automation_loop():
    """
    Every 10 s evaluate rules for living room:
      - Temp ≥ 35 + occupied → AC ON, Fan OFF
      - Temp ≥ 30 + occupied → Fan ON
      - Temp < 30 → Fan OFF, AC OFF
      - Nighttime + occupied → Lamp ON
      - Not occupied (room empty) → all appliances OFF after PIR_TIMEOUT_SEC
      - Away mode → everything off (handled by set_away endpoint)
    Manual overrides block automation for MANUAL_OVERRIDE_SEC seconds.
    """
    while True:
        time.sleep(10)
        ir_actions = []
        with state_lock:
            if STATE["away_mode"]:
                continue

            occupied = STATE["living_room"]["occupied"]
            temp     = STATE["living_room"]["temp"]
            now      = time.time()

            # ── Vacancy shutoff ────────────────────────────────────────────
            if not occupied:
                for app_id in list(STATE["living_room"]["appliances"].keys()):
                    exp = STATE["living_room"]["overrides"].get(app_id, 0)
                    if now >= exp:   # override expired or never set
                        if set_appliance(app_id, False):
                            ir_actions.append((app_id, False))
                # fall through to send IR outside lock

            else:
                # ── Temperature rules ──────────────────────────────────────────
                if temp is not None:
                    t_ac  = lr_cfg("temp_ac_threshold")
                    t_fan = lr_cfg("temp_fan_threshold")
                    if temp >= t_ac:
                        if set_appliance("ac",  True):  ir_actions.append(("ac",  True))
                        if set_appliance("fan", False): ir_actions.append(("fan", False))
                    elif temp >= t_fan:
                        if set_appliance("fan", True):  ir_actions.append(("fan", True))
                        if set_appliance("ac",  False): ir_actions.append(("ac",  False))
                    else:
                        if set_appliance("fan", False): ir_actions.append(("fan", False))
                        if set_appliance("ac",  False): ir_actions.append(("ac",  False))

                # ── Nighttime lamp ─────────────────────────────────────────────
                if is_nighttime():
                    set_appliance("lamp", True)
                else:
                    set_appliance("lamp", False)

        # Send IR outside the lock so it never blocks state_lock
        for app_id, val in ir_actions:
            send_ir(app_id, val)

# ── MQTT ──────────────────────────────────────────────────────────────────────

mqtt_client = None   # set in main

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected (rc={rc})")
    client.subscribe(TOPICS["bedroom"]["pir"])
    client.subscribe(TOPICS["bedroom"]["dht"])
    client.subscribe(TOPICS["bedroom"]["appliances"])
    client.subscribe(TOPICS["kitchen"]["ultrasonic"])

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    topic = msg.topic
    with state_lock:
        if topic == TOPICS["bedroom"]["pir"]:
            STATE["bedroom"]["occupied"] = bool(payload.get("motion", False))

        elif topic == TOPICS["bedroom"]["dht"]:
            STATE["bedroom"]["temp"]     = payload.get("temp")
            STATE["bedroom"]["humidity"] = payload.get("humidity")

        elif topic == TOPICS["bedroom"]["appliances"]:
            STATE["bedroom"]["appliances"].update(payload)

        elif topic == TOPICS["kitchen"]["ultrasonic"]:
            dist = payload.get("distance_cm")
            if dist is not None:
                STATE["kitchen"]["occupied"] = dist < ULTRASONIC_PRESENCE_CM

def setup_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER_IP, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client

# ── IR ────────────────────────────────────────────────────────────────────────

def send_ir(appliance: str, on: bool):
    try:
        from ir_controller import send_code
        send_code(f"living_room_{appliance}_{'on' if on else 'off'}", tx_gpio=IR_TX_PIN)
    except Exception as e:
        print(f"[IR] {e}")

# ── Flask API ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

def build_rooms(s: dict) -> list:
    return [
        {
            "id":       "living-room",
            "name":     "Living Room",
            "pi":       "Pi 1",
            "occupied": s["living_room"]["occupied"],
            "temp":     s["living_room"]["temp"],
            "humidity": s["living_room"]["humidity"],
            "hasDHT":   True,
            "hasIR":    True,
            "appliances": [
                {"id": "tv",   "name": "TV",   "icon": "tv",   "on": s["living_room"]["appliances"]["tv"]},
                {"id": "ac",   "name": "AC",   "icon": "ac",   "on": s["living_room"]["appliances"]["ac"]},
                {"id": "fan",  "name": "Fan",  "icon": "fan",  "on": s["living_room"]["appliances"]["fan"]},
                {"id": "lamp", "name": "Lamp", "icon": "lamp", "on": s["living_room"]["appliances"]["lamp"]},
            ],
        },
        {
            "id":       "bedroom",
            "name":     "Bedroom",
            "pi":       "Pi 2",
            "occupied": s["bedroom"]["occupied"],
            "temp":     s["bedroom"]["temp"],
            "humidity": s["bedroom"]["humidity"],
            "hasDHT":   True,
            "hasIR":    True,
            "appliances": [
                {"id": "ac",   "name": "AC",   "icon": "ac",   "on": s["bedroom"]["appliances"]["ac"]},
                {"id": "lamp", "name": "Lamp", "icon": "lamp", "on": s["bedroom"]["appliances"]["lamp"]},
            ],
        },
        {
            "id":       "kitchen",
            "name":     "Kitchen",
            "pi":       "Pi 3",
            "occupied": s["kitchen"]["occupied"],
            "hasDHT":   False,
            "hasIR":    False,
            "appliances": [
                {"id": "lamp", "name": "Lamp", "icon": "lamp", "on": s["kitchen"]["appliances"]["lamp"]},
            ],
        },
    ]

@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    with state_lock:
        snapshot = json.loads(json.dumps(STATE))   # deep copy
    return jsonify({"rooms": build_rooms(snapshot), "awayMode": snapshot["away_mode"]})


@app.route("/api/rooms/<room_id>/appliances/<appliance_id>", methods=["POST"])
def toggle_appliance(room_id, appliance_id):
    data = request.get_json()
    on   = bool(data.get("on", False))
    send_ir_after = False

    with state_lock:
        if room_id == "living-room" and appliance_id in STATE["living_room"]["appliances"]:
            send_ir_after = set_appliance(appliance_id, on, manual=True)

        elif room_id == "bedroom" and appliance_id in STATE["bedroom"]["appliances"]:
            STATE["bedroom"]["appliances"][appliance_id] = on
            mqtt_client.publish(
                TOPICS["bedroom"]["command"],
                json.dumps({"appliance": appliance_id, "on": on, "manual": True}),
            )

        elif room_id == "kitchen" and appliance_id in STATE["kitchen"]["appliances"]:
            STATE["kitchen"]["appliances"][appliance_id] = on
            mqtt_client.publish(
                TOPICS["kitchen"]["command"],
                json.dumps({"appliance": appliance_id, "on": on}),
            )

    if send_ir_after:
        send_ir(appliance_id, on)

    return jsonify({"ok": True})


@app.route("/api/config", methods=["GET"])
def get_config():
    with config_lock:
        return jsonify({k: dict(v) for k, v in ROOM_CONFIGS.items()})


@app.route("/api/config", methods=["POST"])
def update_config():
    data     = request.get_json() or {}
    room_id  = data.pop("room_id", None)        # e.g. "living-room" / "bedroom" / "kitchen"
    rooms_to_update = [room_id] if room_id else list(ROOM_CONFIGS.keys())

    with config_lock:
        for rid in rooms_to_update:
            if rid not in ROOM_CONFIGS:
                continue
            for key, val in data.items():
                if key in ROOM_CONFIGS[rid]:
                    ROOM_CONFIGS[rid][key] = val

    # Broadcast updated configs to Pi 2 and Pi 3 via MQTT
    if room_id in (None, "bedroom"):
        with config_lock:
            mqtt_client.publish(TOPICS["config"],
                                json.dumps({"room_id": "bedroom", **ROOM_CONFIGS["bedroom"]}))
    if room_id in (None, "kitchen"):
        with config_lock:
            mqtt_client.publish(TOPICS["config"],
                                json.dumps({"room_id": "kitchen", **ROOM_CONFIGS["kitchen"]}))

    return jsonify({"ok": True})


@app.route("/api/away", methods=["POST"])
def set_away():
    data   = request.get_json()
    active = bool(data.get("active", False))

    with state_lock:
        STATE["away_mode"] = active
        if active:
            for k in STATE["living_room"]["appliances"]:
                STATE["living_room"]["appliances"][k] = False
                _apply_gpio(k, False)
                if k in ("tv", "ac", "fan"):
                    send_ir(k, False)
            for k in STATE["bedroom"]["appliances"]:
                STATE["bedroom"]["appliances"][k] = False

    # Notify other Pis
    mqtt_client.publish(TOPICS["bedroom"]["command"], json.dumps({"away": active}))
    mqtt_client.publish(TOPICS["kitchen"]["command"], json.dumps({"away": active}))

    return jsonify({"ok": True})

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[Pi 1] Starting Living Room node")

    mqtt_client = setup_mqtt()

    def energy_led_loop():
        while True:
            update_energy_led()
            time.sleep(2)

    threading.Thread(target=pir_loop,        daemon=True).start()
    threading.Thread(target=dht_loop,        daemon=True).start()
    threading.Thread(target=automation_loop, daemon=True).start()
    threading.Thread(target=energy_led_loop, daemon=True).start()

    print(f"[Pi 1] Flask API on http://0.0.0.0:{FLASK_PORT}")
    try:
        app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)
    finally:
        _pwm_r.stop()
        _pwm_g.stop()
        _pwm_b.stop()
        GPIO.cleanup()

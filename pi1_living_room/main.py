#!/usr/bin/env python3
"""
Pi 1 — Living Room
Role : Central server + MQTT broker host + living room sensors
Sensors : PIR (GPIO 24), DHT22 (GPIO 23),
          IR Sensor A (GPIO 17), IR Sensor B (GPIO 18),
          RGB LED (GPIO 27/22/12), TV relay (GPIO 5), AC relay (GPIO 6), Fan relay (GPIO 13)
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
    NIGHT_START_MIN, PIR_TIMEOUT_SEC,
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

PIR_PIN      = 24
DHT_PIN      = 23
SENSOR_A_PIN = 17   # IR sensor A — triggers first when entering
SENSOR_B_PIN = 18   # IR sensor B — triggers first when leaving
TV_PIN       = 5
AC_PIN       = 6
FAN_PIN      = 13
RGB_RED      = 27
RGB_GREEN    = 22
RGB_BLUE     = 12

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(PIR_PIN,      GPIO.IN)
GPIO.setup(SENSOR_A_PIN, GPIO.IN)
GPIO.setup(SENSOR_B_PIN, GPIO.IN)
GPIO.setup(TV_PIN,    GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(AC_PIN,    GPIO.OUT, initial=GPIO.LOW)
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
        lr_occupied    = STATE["living_room"]["occupied"]
        lr_appliances  = dict(STATE["living_room"]["appliances"])   # copy, not reference
        bed_occupied   = STATE["bedroom"]["occupied"]
        bed_appliances = dict(STATE["bedroom"]["appliances"])       # copy, not reference

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
        "appliances":  {"tv": False, "ac": False, "fan": False},
        "overrides":   {},          # appliance_id -> expiry timestamp
    },
    "bedroom": {
        "occupied":    False,
        "last_motion": 0,       # timestamp of last motion pulse from Pi 2
        "temp":        None,
        "humidity":    None,
        "appliances":  {"ac": False, "lamp": False},
    },
    "kitchen": {
        "occupied":  False,
        "last_seen": 0,
        "appliances": {"lamp": False},
    },
    "away_mode":      False,
    "household_size": 3,    # configurable from dashboard
    "occupant_count": 3,    # starts equal to household_size
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_nighttime() -> bool:
    now = datetime.now()
    current = now.hour * 60 + now.minute
    sh, sm = map(int, lr_cfg("night_start").split(":"))
    eh, em = map(int, lr_cfg("night_end").split(":"))
    start = sh * 60 + sm
    end   = eh * 60 + em
    if start > end:   # night spans midnight (e.g. 19:30 → 07:30)
        return current >= start or current < end
    else:             # same-day window (e.g. 08:00 → 20:00)
        return start <= current < end

def _apply_gpio(appliance_id: str, on: bool):
    """Drive relay for each appliance."""
    if appliance_id == "tv":
        GPIO.output(TV_PIN,  GPIO.HIGH if on else GPIO.LOW)
    elif appliance_id == "ac":
        GPIO.output(AC_PIN,  GPIO.HIGH if on else GPIO.LOW)
    elif appliance_id == "fan":
        GPIO.output(FAN_PIN, GPIO.HIGH if on else GPIO.LOW)

def set_appliance(appliance_id: str, on: bool, manual: bool = False):
    """
    Update appliance state and drive GPIO relay.
    Must be called while state_lock is held.
    """
    if manual:
        STATE["living_room"]["overrides"][appliance_id] = time.time() + lr_cfg("manual_override_sec")
    else:
        # automation — do not apply if a live manual override exists
        exp = STATE["living_room"]["overrides"].get(appliance_id, 0)
        if time.time() < exp:
            return
    STATE["living_room"]["appliances"][appliance_id] = on
    _apply_gpio(appliance_id, on)

# ── IR entry/exit counter ─────────────────────────────────────────────────────

DIRECTION_WINDOW_SEC = 1.5   # max seconds between the two sensor triggers

_ir_ts   = {"a": 0.0, "b": 0.0}
_ir_lock = threading.Lock()

def _all_appliances_off():
    """Force every appliance off across all rooms (house empty)."""
    with state_lock:
        STATE["living_room"]["overrides"].clear()
        for k in STATE["living_room"]["appliances"]:
            STATE["living_room"]["appliances"][k] = False
            _apply_gpio(k, False)
        for k in STATE["bedroom"]["appliances"]:
            STATE["bedroom"]["appliances"][k] = False
        for k in STATE["kitchen"]["appliances"]:
            STATE["kitchen"]["appliances"][k] = False
    mqtt_client.publish(TOPICS["bedroom"]["command"], json.dumps({"all_off": True}))
    mqtt_client.publish(TOPICS["kitchen"]["command"],  json.dumps({"all_off": True}))
    print("[IR] House empty — all appliances off")

def _handle_enter():
    with state_lock:
        if STATE["occupant_count"] < STATE["household_size"]:
            STATE["occupant_count"] += 1
        count = STATE["occupant_count"]
        size  = STATE["household_size"]
    print(f"[IR] Person entered  → {count}/{size} home")

def _handle_leave():
    turn_off = False
    with state_lock:
        if STATE["occupant_count"] > 0:
            STATE["occupant_count"] -= 1
        count = STATE["occupant_count"]
        size  = STATE["household_size"]
        if count == 0:
            turn_off = True
    print(f"[IR] Person left     → {count}/{size} home")
    if turn_off:
        _all_appliances_off()

def ir_entry_exit_loop():
    """
    Poll both IR sensors at 50 Hz.
    Detects direction by which sensor breaks first:
      A then B (within DIRECTION_WINDOW_SEC) → entering
      B then A (within DIRECTION_WINDOW_SEC) → leaving
    Sensors output LOW when object detected.
    """
    prev_a = GPIO.HIGH
    prev_b = GPIO.HIGH

    while True:
        a   = GPIO.input(SENSOR_A_PIN)
        b   = GPIO.input(SENSOR_B_PIN)
        now = time.time()
        action = None

        with _ir_lock:
            # Detect falling edge (HIGH → LOW = object detected)
            if prev_a == GPIO.HIGH and a == GPIO.LOW:
                _ir_ts["a"] = now
            if prev_b == GPIO.HIGH and b == GPIO.LOW:
                _ir_ts["b"] = now

            ta = _ir_ts["a"]
            tb = _ir_ts["b"]

            if ta > 0 and tb > 0:
                diff = tb - ta
                if 0 < diff <= DIRECTION_WINDOW_SEC:       # A first → entering
                    _ir_ts["a"] = _ir_ts["b"] = 0.0
                    action = "enter"
                elif -DIRECTION_WINDOW_SEC <= diff < 0:    # B first → leaving
                    _ir_ts["a"] = _ir_ts["b"] = 0.0
                    action = "leave"

            # Clear stale timestamps
            if ta > 0 and now - ta > DIRECTION_WINDOW_SEC * 2:
                _ir_ts["a"] = 0.0
            if tb > 0 and now - tb > DIRECTION_WINDOW_SEC * 2:
                _ir_ts["b"] = 0.0

        if action == "enter":
            _handle_enter()
        elif action == "leave":
            _handle_leave()

        prev_a = a
        prev_b = b
        time.sleep(0.02)   # 50 Hz

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
        with state_lock:
            if STATE["away_mode"] or STATE["occupant_count"] == 0:
                continue

            occupied = STATE["living_room"]["occupied"]
            temp     = STATE["living_room"]["temp"]
            now      = time.time()

            # ── Vacancy shutoff ────────────────────────────────────────────
            if not occupied:
                for app_id in list(STATE["living_room"]["appliances"].keys()):
                    exp = STATE["living_room"]["overrides"].get(app_id, 0)
                    if now >= exp:   # override expired or never set
                        set_appliance(app_id, False)

            else:
                # ── Temperature rules ──────────────────────────────────────────
                if temp is not None:
                    t_ac  = lr_cfg("temp_ac_threshold")
                    t_fan = lr_cfg("temp_fan_threshold")
                    if temp >= t_ac:
                        set_appliance("ac",  True)
                        set_appliance("fan", False)
                    elif temp >= t_fan:
                        set_appliance("fan", True)
                        set_appliance("ac",  False)
                    else:
                        set_appliance("fan", False)
                        set_appliance("ac",  False)

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
            if payload.get("motion", False):
                STATE["bedroom"]["last_motion"] = time.time()
                STATE["bedroom"]["occupied"] = True
            else:
                with config_lock:
                    timeout = ROOM_CONFIGS["bedroom"]["pir_timeout_sec"]
                if time.time() - STATE["bedroom"]["last_motion"] > timeout:
                    STATE["bedroom"]["occupied"] = False

        elif topic == TOPICS["bedroom"]["dht"]:
            STATE["bedroom"]["temp"]     = payload.get("temp")
            STATE["bedroom"]["humidity"] = payload.get("humidity")

        elif topic == TOPICS["bedroom"]["appliances"]:
            STATE["bedroom"]["appliances"].update(payload)

        elif topic == TOPICS["kitchen"]["ultrasonic"]:
            dist = payload.get("distance_cm")
            if dist is not None:
                if dist < ULTRASONIC_PRESENCE_CM:
                    STATE["kitchen"]["last_seen"] = time.time()
                    STATE["kitchen"]["occupied"]  = True
                else:
                    with config_lock:
                        timeout = ROOM_CONFIGS["kitchen"]["pir_timeout_sec"]
                    if time.time() - STATE["kitchen"]["last_seen"] > timeout:
                        STATE["kitchen"]["occupied"] = False
            lamp = payload.get("lamp")
            if lamp is not None:
                STATE["kitchen"]["appliances"]["lamp"] = lamp

def setup_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER_IP, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client

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
            "appliances": [
                {"id": "tv",  "name": "TV",  "icon": "tv",  "on": s["living_room"]["appliances"]["tv"]},
                {"id": "ac",  "name": "AC",  "icon": "ac",  "on": s["living_room"]["appliances"]["ac"]},
                {"id": "fan", "name": "Fan", "icon": "fan", "on": s["living_room"]["appliances"]["fan"]},
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
            "appliances": [
                {"id": "lamp", "name": "Lamp", "icon": "lamp", "on": s["kitchen"]["appliances"]["lamp"]},
            ],
        },
    ]

@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    with state_lock:
        snapshot = json.loads(json.dumps(STATE))   # deep copy
    return jsonify({
        "rooms":         build_rooms(snapshot),
        "awayMode":      snapshot["away_mode"],
        "occupantCount": snapshot["occupant_count"],
        "householdSize": snapshot["household_size"],
    })


@app.route("/api/rooms/<room_id>/appliances/<appliance_id>", methods=["POST"])
def toggle_appliance(room_id, appliance_id):
    data = request.get_json()
    on   = bool(data.get("on", False))

    with state_lock:
        if room_id == "living-room" and appliance_id in STATE["living_room"]["appliances"]:
            set_appliance(appliance_id, on, manual=True)

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


@app.route("/api/household", methods=["POST"])
def set_household():
    data = request.get_json()
    size = max(1, int(data.get("size", 1)))
    with state_lock:
        STATE["household_size"] = size
        STATE["occupant_count"] = size   # reset — assume everyone is home
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
            for k in STATE["bedroom"]["appliances"]:
                STATE["bedroom"]["appliances"][k] = False
            for k in STATE["kitchen"]["appliances"]:
                STATE["kitchen"]["appliances"][k] = False

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

    threading.Thread(target=pir_loop,           daemon=True).start()
    threading.Thread(target=dht_loop,           daemon=True).start()
    threading.Thread(target=automation_loop,    daemon=True).start()
    threading.Thread(target=energy_led_loop,    daemon=True).start()
    threading.Thread(target=ir_entry_exit_loop, daemon=True).start()

    print(f"[Pi 1] Flask API on http://0.0.0.0:{FLASK_PORT}")
    try:
        app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)
    finally:
        _pwm_r.stop()
        _pwm_g.stop()
        _pwm_b.stop()
        GPIO.cleanup()

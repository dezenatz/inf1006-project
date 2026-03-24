#!/usr/bin/env python3
"""
Pi 3 — Kitchen
Role    : Sensor node
Sensors : Ultrasonic TRIG/ECHO (GPIO 23/24), LED (GPIO 27/22), Lamp relay (GPIO 6)
"""

import json
import os
import sys
import time

import threading

import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    MANUAL_OVERRIDE_SEC, MQTT_BROKER_IP, MQTT_PORT,
    PIR_TIMEOUT_SEC, SENSOR_PUBLISH_INTERVAL, TOPICS, ULTRASONIC_PRESENCE_CM,
)

# ── Runtime config ─────────────────────────────────────────────────────────────

RUNTIME_CONFIG = {
    "pir_timeout_sec": PIR_TIMEOUT_SEC,
}

# ── GPIO ──────────────────────────────────────────────────────────────────────

TRIG_PIN  = 23
ECHO_PIN  = 24
LAMP_PIN  = 6

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(TRIG_PIN,  GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(ECHO_PIN,  GPIO.IN)
GPIO.setup(LAMP_PIN,  GPIO.OUT, initial=GPIO.LOW)

# ── State ─────────────────────────────────────────────────────────────────────

state_lock          = threading.Lock()
away_mode           = False
occupied            = False
last_seen_time      = 0.0   # timestamp of last detected presence
manual_lamp         = None  # None = auto, True/False = manual override
manual_lamp_expiry  = 0.0   # timestamp when manual override expires

# ── Lamp ──────────────────────────────────────────────────────────────────────

def set_lamp(on: bool):
    GPIO.output(LAMP_PIN, GPIO.HIGH if on else GPIO.LOW)

# ── Ultrasonic ────────────────────────────────────────────────────────────────

def read_ultrasonic():
    """Return distance in cm, or None on timeout."""
    GPIO.output(TRIG_PIN, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG_PIN, GPIO.LOW)

    deadline = time.time() + 0.04
    while GPIO.input(ECHO_PIN) == 0:
        if time.time() > deadline:
            return None
    pulse_start = time.time()

    deadline = time.time() + 0.04
    while GPIO.input(ECHO_PIN) == 1:
        if time.time() > deadline:
            return None
    pulse_end = time.time()

    return round((pulse_end - pulse_start) * 17150, 1)

# ── MQTT ──────────────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected (rc={rc})")
    client.subscribe(TOPICS["kitchen"]["command"])
    client.subscribe(TOPICS["config"])

def on_message(client, userdata, msg):
    global away_mode, manual_lamp, manual_lamp_expiry
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    if msg.topic == TOPICS["config"]:
        if payload.get("room_id") == "kitchen" and "pir_timeout_sec" in payload:
            with state_lock:
                RUNTIME_CONFIG["pir_timeout_sec"] = payload["pir_timeout_sec"]
        return

    if "away" in payload:
        with state_lock:
            away_mode = payload["away"]
            if away_mode:
                manual_lamp = None
        if payload["away"]:
            set_lamp(False)
        return

    if payload.get("all_off"):
        with state_lock:
            manual_lamp = False
            manual_lamp_expiry = time.time() + MANUAL_OVERRIDE_SEC
        set_lamp(False)
        return

    if payload.get("appliance") == "lamp":
        with state_lock:
            manual_lamp = bool(payload.get("on", False))
            manual_lamp_expiry = time.time() + MANUAL_OVERRIDE_SEC
            _away = away_mode
        if not _away:
            set_lamp(manual_lamp)

# ── Main loop ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[Pi 3] Starting Kitchen node")

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER_IP, MQTT_PORT, keepalive=60)
    client.loop_start()

    try:
        while True:
            distance = read_ultrasonic()

            if distance is not None:
                person_present = distance < ULTRASONIC_PRESENCE_CM

                with state_lock:
                    if person_present:
                        last_seen_time = time.time()
                        occupied = True
                    else:
                        if time.time() - last_seen_time > RUNTIME_CONFIG["pir_timeout_sec"]:
                            occupied = False

                    # Expire manual override once its window has passed
                    if manual_lamp is not None and time.time() >= manual_lamp_expiry:
                        manual_lamp = None

                    _away        = away_mode
                    _occupied    = occupied
                    _manual_lamp = manual_lamp

                if not _away:
                    if _manual_lamp is None:
                        set_lamp(_occupied)   # lamp follows presence automatically
                    else:
                        set_lamp(_manual_lamp)  # respect manual override

                client.publish(
                    TOPICS["kitchen"]["ultrasonic"],
                    json.dumps({
                        "distance_cm": distance,
                        "lamp": GPIO.input(LAMP_PIN) == GPIO.HIGH,
                    }),
                )
                print(f"[Ultrasonic] {distance} cm  occupied={_occupied}")

            time.sleep(SENSOR_PUBLISH_INTERVAL)

    finally:
        GPIO.cleanup()

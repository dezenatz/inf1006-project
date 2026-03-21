# Smart Home Setup Guide
### For Pi 1 (Living Room), Pi 2 (Bedroom), Pi 3 (Kitchen)

---

## Before You Start
- All 3 Raspberry Pis must be connected to the **same WiFi network**
- You need a monitor, keyboard, and mouse connected to each Pi (or use SSH)
- Make sure each Pi is powered on

---

## STEP 1 — Open the Terminal
On each Raspberry Pi, look for the **Terminal** icon on the taskbar (it looks like a black screen with `>_`). Click it to open.

---

## STEP 2 — Update the Pi
Run this on **all 3 Pis**:
```bash
sudo apt update && sudo apt upgrade -y
```
This may take a few minutes. Wait for it to finish.

---

## STEP 3 — Install Git
Run this on **all 3 Pis**:
```bash
sudo apt install git -y
```

---

## STEP 4 — Download the Code
Run this on **all 3 Pis**:
```bash
cd ~
git clone https://github.com/dezenatz/inf1006-project.git
cd inf1006-project
```
You should now see the project files. You can verify by typing `ls` and pressing Enter.

---

## STEP 5 — Find Pi 1's IP Address (Do this on Pi 1 only)
On **Pi 1**, run:
```bash
hostname -I
```
You will see something like `192.168.1.105`. **Write this number down** — you will need it for the next step.

---

## STEP 6 — Update the Config File (Do this on all 3 Pis)
You need to tell all Pis where Pi 1 is. Open the config file:
```bash
nano config.py
```
Find the line that says:
```
MQTT_BROKER_IP = "192.168.1.100"
```
Change the number to the IP address you wrote down in Step 5. For example:
```
MQTT_BROKER_IP = "192.168.1.105"
```
To save: press **Ctrl + X**, then press **Y**, then press **Enter**.

---

## STEP 7 — Install Dependencies

### On Pi 1 (Living Room):
```bash
sudo apt install mosquitto mosquitto-clients -y
sudo systemctl enable mosquitto
sudo systemctl start mosquitto
pip3 install paho-mqtt flask flask-cors Adafruit_DHT
```

### On Pi 2 (Bedroom):
```bash
pip3 install paho-mqtt Adafruit_DHT
```

### On Pi 3 (Kitchen):
```bash
pip3 install paho-mqtt
```

---

## STEP 8 — Run the Code

Open a terminal on each Pi and run the command for that Pi.

### Pi 1 (Living Room) — run this FIRST:
```bash
cd ~/inf1006-project
python3 pi1_living_room/main.py
```
You should see:
```
[Pi 1] Starting Living Room node
[MQTT] Connected (rc=0)
[Pi 1] Flask API on http://0.0.0.0:5000
```

### Pi 2 (Bedroom):
```bash
cd ~/inf1006-project
python3 pi2_bedroom/main.py
```
You should see:
```
[Pi 2] Starting Bedroom node
[MQTT] Connected (rc=0)
```

### Pi 3 (Kitchen):
```bash
cd ~/inf1006-project
python3 pi3_kitchen/main.py
```
You should see:
```
[Pi 3] Starting Kitchen node
[MQTT] Connected (rc=0)
```

---

## STEP 9 — Getting Updates
If there are any code changes pushed, run this on each Pi:
```bash
cd ~/inf1006-project
git pull
```
Then restart the Python script.

---

## Troubleshooting

**"Command not found" when running python3:**
```bash
sudo apt install python3 python3-pip -y
```

**"MQTT Connected" not showing / connection refused:**
- Make sure Pi 1 is running first
- Double check the IP address in `config.py` matches Pi 1's actual IP
- Make sure all Pis are on the same WiFi

**"ModuleNotFoundError: No module named 'xxx'":**
- Re-run the pip3 install command for that Pi (Step 7)

**To stop a running script:**
- Press **Ctrl + C** in the terminal

import os
import sys
import time
import json
import logging
import requests
import paho.mqtt.client as mqtt
import threading
from ka3005p import PowerSupply

# Config
DEVICE_ACCESS_TOKEN = "t00000b00000i00000k8" # CHANGE THIS
SERIAL_PORT = "/dev/serial/by-id/usb-Nuvoton_USB_Virtual_COM_000962640452-if00" # CHANGE THIS. See the info int he README
MQTT_HOST = "yourhost.net" # CHANGE THIS
MQTT_PORT = 1883
MAX_CURRENT = 5.0 # Max current of the KA3005P in A
VOLTAGE_SETPOINT = 30.0 # Volts - A fixed voltage to enable current control mode

# Globals
mode = "manual"
manual_current_pct = 0
profile_data = []
profile_status = "idle"
profile_thread = None
profile_url = ""
psu = None # Initialize psu to None before the try block

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# KA3005P Controller Setup
try:
    psu = PowerSupply(SERIAL_PORT)
    psu.voltage = VOLTAGE_SETPOINT
    psu.current = 0.0
    psu.enable()
    logging.info(f"Connected to PSU at {SERIAL_PORT}. Output is ON.")
except Exception as e:
    logging.error(f"Failed to connect to power supply: {e}")

# ThingsBoard MQTT bits
def on_connect(client, userdata, flags, reasonCode, properties):
    logging.info(f"Connected to ThingsBoard Edge with result code {reasonCode}")
    client.subscribe("v1/devices/me/attributes")
    
    # Request all shared attributes to sync local state with server dashboard state
    client.publish("v1/devices/me/attributes/request/1", json.dumps({"sharedKeys": "controllerMode,manualCurrentPct"}))

def on_message(client, userdata, msg):
    global mode, manual_current_pct, profile_url, profile_data, profile_status, profile_thread
    
    topic = msg.topic
    payload = json.loads(msg.payload.decode("utf-8"))
    
    logging.info(f"Message received on topic {topic}: {payload}")

    attributes = payload.get('shared', payload)
    
    # Check for mode change (manual  or auto)
    if "controllerMode" in attributes:
        mode = attributes["controllerMode"]
        logging.info(f"Controller mode switched to: {mode}")
        
        if mode == "manual" and profile_thread and profile_thread.is_alive():
            logging.warning("Automated profile cancelled due to mode switch.")
            profile_status = "idle"
            client.publish("v1/devices/me/attributes", json.dumps({"profileStatus": profile_status}))

    # Check for manual current change
    if "manualCurrentPct" in attributes:
        manual_current_pct = attributes["manualCurrentPct"]
        
    # Check for power profile URL change
    if "profileUrl" in attributes:
        profile_url = attributes["profileUrl"]

    # Check for new power profile trigger
    if "newProfileReady" in attributes and attributes["newProfileReady"] == True:
        if profile_url:
            client.publish("v1/devices/me/attributes", json.dumps({"newProfileReady": False}))
            
            if profile_thread and profile_thread.is_alive():
                logging.warning("New profile request received, but a profile is already running.")
                return
            
            profile_thread = threading.Thread(target=run_automated_profile)
            profile_thread.start()

        else:
            logging.warning("New profile flag set but URL is missing.")

def run_automated_profile():
    global profile_data, profile_status, mode, psu, client
    
    if mode != "auto":
        logging.warning("Cannot start automated profile: Controller not in 'auto' mode.")
        profile_status = "idle"
        client.publish("v1/devices/me/attributes", json.dumps({"profileStatus": profile_status}))
        return
    
    if not psu:
        logging.error("Cannot start automated profile: Power supply not connected.")
        profile_status = "idle"
        client.publish("v1/devices/me/attributes", json.dumps({"profileStatus": profile_status}))
        return

    try:
      # Download and parse the power profile csv from the specified URL
        profile_status = "downloading"
        client.publish("v1/devices/me/attributes", json.dumps({"profileStatus": profile_status}))
        
        response = requests.get(profile_url, timeout=10)
        response.raise_for_status()
        
        csv_data = response.text.strip().split('\n')
        profile_data = []
        for line in csv_data[1:]:
            duration, power_pct = line.split(',')
            profile_data.append({"duration": int(duration), "power_pct": int(power_pct)})
            
        logging.info("Power profile downloaded and parsed successfully.")
        
    except requests.exceptions.RequestException as e:
        profile_status = "download_error"
        client.publish("v1/devices/me/attributes", json.dumps({"profileStatus": profile_status}))
        logging.error(f"Error downloading profile from {profile_url}: {e}")
        return
    except Exception as e:
        profile_status = "parsing_error"
        client.publish("v1/devices/me/attributes", json.dumps({"profileStatus": profile_status}))
        logging.error(f"Error parsing profile data: {e}")
        return
    
    logging.info("Automated profile execution started.")
    profile_status = "executing"
    client.publish("v1/devices/me/attributes", json.dumps({"profileStatus": profile_status}))

  # run the power profile
    for step in profile_data:
        if mode != "auto":
            logging.info("Automated profile execution interrupted by user.")
            break
        
        power_pct = step["power_pct"]
        duration_s = step["duration"]
        
        target_current = (power_pct / 100.0) * MAX_CURRENT
        
        logging.info(f"Setting current to {target_current:.2f}A ({power_pct}%) for {duration_s} seconds.")
        try:
            psu.current = target_current
            client.publish("v1/devices/me/telemetry", json.dumps({"psu_commandedCurrent": target_current}))
        except Exception as e:
            logging.error(f"Failed to set current: {e}")
            
        time.sleep(duration_s)
        
    logging.info("Automated profile execution finished.")
    profile_status = "idle"
    client.publish("v1/devices/me/attributes", json.dumps({"profileStatus": profile_status}))

def main_loop():
    global mode, manual_current_pct, psu, client
    
    while True:
        try:
            commanded_current = 0

          # manually control PSU
            if mode == "manual":
                if psu:
                    target_current = (manual_current_pct / 100.0) * MAX_CURRENT
                    psu.current = target_current
                    commanded_current = target_current
                else:
                    commanded_current = (manual_current_pct / 100.0) * MAX_CURRENT
            
            elif mode == "auto":
                if psu:
                    commanded_current = psu.current

          # get and publish the telemety from the PSU reported values
            if psu:
                voltage_v = psu.voltage
                current_a = psu.current
                power_w = voltage_v * current_a

                telemetry = {
                    "psu_voltage": voltage_v,
                    "psu_current": current_a,
                    "psu_power": power_w,
                    "psu_commandedCurrent": commanded_current
                }
                client.publish("v1/devices/me/telemetry", json.dumps(telemetry))
            else:
                telemetry = {
                    "psu_commandedCurrent": commanded_current
                }
                client.publish("v1/devices/me/telemetry", json.dumps(telemetry))

        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            
        time.sleep(2)

# Setup MQTT client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=DEVICE_ACCESS_TOKEN)
client.username_pw_set(DEVICE_ACCESS_TOKEN)
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()


try:
    main_loop()
except KeyboardInterrupt:
    logging.info("Exiting script...")
    if psu:
        psu.disable()
    client.loop_stop()
    sys.exit(0)

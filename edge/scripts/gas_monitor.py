# this script is to calculate volume flow rate from a RITTER MilliGascounter https://www.ritter.de/en/products/milligascounters/ 
# from a Raspberry Pi. (I used a Pi 5)
# if you're on Windows and you have the RITTER Signal Interface Module (SIM), you can use RIGAMO.
import time
import json
import os
import paho.mqtt.client as mqtt
from gpiozero import Button # Import Button for switch handling
from signal import pause # For keeping the script alive cleanly
import threading # For the periodic MQTT publishing/flow rate calculation

# Config
GPIO_PIN = 17  # GPIO pin connected to the reed switch
    # REF https://www.ritter.de/en/operation-manuals/operation-manual-mgc
VOLUME_PER_PULSE_ML = 3.26  # CHANGE THIS - Volume of gas per reed switch trigger in mL, check side of the meter used. 


# MQTT Configuration for ThingsBoard Edge
MQTT_BROKER = "localhost"  # ThingsBoard Edge is on the same Pi
MQTT_PORT = 1883           # Default MQTT port for ThingsBoard
THINGSBOARD_ACCESS_TOKEN = "e0000060600000ch0000" # <<< IMPORTANT: REPLACE WITH YOUR DEVICE'S ACCESS TOKEN
TB_MQTT_TELEMETRY_TOPIC = "v1/devices/me/telemetry" # ThingsBoard default telemetry topic
MQTT_CLIENT_ID = "raspberry_pi_gas_monitor" # You might  want to CHANGE THIS

# Measurement intervals
FLOW_RATE_INTERVAL_SECONDS = 30  # Calculate flow rate every __ seconds
MQTT_PUBLISH_INTERVAL_SECONDS = 30  # Publish data to MQTT every __ seconds

# File to store cumulative volume for persistence
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gas_data.json")

# Globals
cumulative_volume_ml = 0.00
pulse_count_current_interval = 0
last_flow_rate_calc_time = time.time()
last_mqtt_publish_time = time.time()
current_flow_rate_ml_per_min = 0.0000
client = None # Global MQTT client instance
gas_sensor = None # Global gpiozero Button object instance



def load_data():
    """Loads cumulative volume from a file."""
    global cumulative_volume_ml
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                cumulative_volume_ml = data.get("cumulative_volume_ml", 0.00)
                print(f"Loaded cumulative volume: {cumulative_volume_ml:.2f} mL")
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading data from {DATA_FILE}: {e}. Starting with 0 volume.")
            cumulative_volume_ml = 0.00
    else:
        print("Data file not found. Starting with 0 volume.")
        cumulative_volume_ml = 0.00

def save_data():
    """Saves cumulative volume to a file."""
    data = {"cumulative_volume_ml": cumulative_volume_ml}
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f)
    except IOError as e:
        print(f"Error saving data to {DATA_FILE}: {e}")

def on_connect(client_instance, userdata, flags, rc):
    """Callback for when the client connects to the MQTT broker."""
    if rc == 0:
        print("Connected to MQTT Broker!")
    else:
        print(f"Failed to connect to MQTT, return code {rc}\n")

def pulse_detected():
    """Callback function for reed switch trigger."""
    global cumulative_volume_ml, pulse_count_current_interval
    
    cumulative_volume_ml += VOLUME_PER_PULSE_ML
    pulse_count_current_interval += 1
    print(f"DEBUG: Pulse detected! Cumulative volume: {cumulative_volume_ml:.2f} mL")
    save_data() # Save after each pulse for better persistence

def calculate_and_publish_data():
    """Calculates gas flow rate and publishes data."""
    global pulse_count_current_interval, last_flow_rate_calc_time, current_flow_rate_ml_per_min, last_mqtt_publish_time
    
    current_time = time.time()
    
    # Calculate flow rate periodically
    time_diff_flow_rate = current_time - last_flow_rate_calc_time
    if time_diff_flow_rate >= FLOW_RATE_INTERVAL_SECONDS:
        print(f"DEBUG: time_diff_flow_rate = {time_diff_flow_rate:.4f} seconds")
        print(f"DEBUG: pulse_count_current_interval = {pulse_count_current_interval} pulses")

        
        volume_in_interval = pulse_count_current_interval * VOLUME_PER_PULSE_ML
        
        if time_diff_flow_rate > 0:
            current_flow_rate_ml_per_min = (volume_in_interval / time_diff_flow_rate) * 60 # Convert to mL/minute
        else:
            current_flow_rate_ml_per_min = 0.0000 # Avoid division by zero
            
        print(f"DEBUG: Calculated flow rate: {current_flow_rate_ml_per_min:.4f} mL/min")
        
        pulse_count_current_interval = 0 # Reset pulse count for next interval
        last_flow_rate_calc_time = current_time

    # Publish to MQTT periodically
    time_diff_mqtt_publish = current_time - last_mqtt_publish_time
    if time_diff_mqtt_publish >= MQTT_PUBLISH_INTERVAL_SECONDS:
        try:
            # Prepare telemetry data as a JSON object for ThingsBoard
            telemetry_data = {
                "totalVolume_ml": round(cumulative_volume_ml, 2),
                "flowRate_ml_per_min": round(current_flow_rate_ml_per_min, 4)
            }
            
            # Publish the JSON data to the ThingsBoard telemetry topic
            client.publish(TB_MQTT_TELEMETRY_TOPIC, json.dumps(telemetry_data), qos=1)
            print(f"DEBUG: Published telemetry to ThingsBoard: {json.dumps(telemetry_data)}")
        except Exception as e:
            print(f"Error publishing to MQTT: {e}")
            # Attempt to reconnect if connection is lost
            try:
                client.reconnect()
            except Exception as re_e:
                print(f"Error during MQTT reconnect attempt: {re_e}")

        last_mqtt_publish_time = current_time

def main():
    global client, gas_sensor
    
    # Load previously saved data
    load_data()

    # GPIO Setup - also see the README
    # Button class represents a push button or switch connected to a GPIO pin.
    # When pull_up=True, gpiozero enables an internal pull-up, so we dont need an external pull up resistor
    # active_state=False means the button is active (pressed/closed) when the pin is LOW (connected to GND).
    # bounce_time can be tweaked if not performing correctly
    # Note close time is supposed to be ±0.1s, so bounce should be less than that. I got good results with 30ms, maybe it could be lower?
    # https://www.ritter.de/en/data-sheets/pulse-generator-v6.0-reed-contact/
    gas_sensor = Button(GPIO_PIN, pull_up=True, bounce_time=0.03)
    
    # Attach the pulse_detected function to the when_pressed event
    gas_sensor.when_pressed = pulse_detected

    # MQTT client setup
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect
    
    # Set ThingsBoard Access Token for authentication
    client.username_pw_set(THINGSBOARD_ACCESS_TOKEN) 
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60) # 60 seconds keepalive
    except Exception as e:
        print(f"Initial connection to MQTT broker failed: {e}")
        # Allow the script to continue and attempt reconnects in the loop
        
    client.loop_start()  # Start the MQTT client loop in a separate thread

    print(f"Monitoring reed switch on GPIO {GPIO_PIN}. Press Ctrl+C to exit.")
    
    try:
        # Schedule the periodic data calculation and publishing
        def periodic_task_scheduler():
            calculate_and_publish_data()
            # Reschedule the timer to run again in 1 second
            # This creates a recurring task without waiting in a loop
            threading.Timer(1.0, periodic_task_scheduler).start()

        # Start the periodic task immediately
        periodic_task_scheduler()

        # Use pause() to keep the main thread alive, waiting for GPIO events and the timer
        pause() 

    except KeyboardInterrupt:
        print("\nExiting program due to Keyboard Interrupt.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        save_data() # Save data one last time on exit
        if gas_sensor:
            gas_sensor.close() # Clean up gpiozero pins
            print("GPIO pins cleaned up.")
        if client: # Ensure client exists before attempting to stop and disconnect
            client.loop_stop()
            client.disconnect()
            print("MQTT client disconnected.")

if __name__ == "__main__":
    main()

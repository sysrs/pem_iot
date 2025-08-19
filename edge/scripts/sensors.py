# This script will gather a telemetry from a bunch of sensors on a Pi 5 and then publish to MQTT for ThingsBoard
import board
import busio
import adafruit_ina260
import adafruit_sht4x
import adafruit_bmp280
import os
import glob
import time
import json
import paho.mqtt.client as mqtt

# MQTT Config - in my case, TB Edge is in a docker onctonter on the Pi. This scritp runs on the host. 
# MQTT port is availible from the host to the docker container - See README
THINGSBOARD_EDGE_HOST = "localhost" # Set to your server
THINGSBOARD_EDGE_PORT = 1883
THINGSBOARD_EDGE_ACCESS_TOKEN = "f00000E00000W000000dE" # CHANGE THIS - get it from your ThingsBoard Edge Device

# Setup sensors
# I2C Bus for INA260, SHT40, BMP280
i2c = busio.I2C(board.SCL, board.SDA)
ina260 = adafruit_ina260.INA260(i2c, address=0x40) #  CHANGE THIS - use `i2cdetect -y 1` to check address 
sht40 = adafruit_sht4x.SHT4x(i2c)
bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address=0x76) # CHANGE THIS - use `i2cdetect -y 1` to check address 

time.sleep(0.1) # Wait 100 milliseconds for sensors to settle - things weren't stable when this was added. might not need it. 

# 1-Wire Setup for DS18B20s
base_dir = '/sys/bus/w1/devices/'
# Find all devices starting with '28-' (DS18B20 sensors) - (This might not be the best way to do this, but it's working.)
device_folders = glob.glob(base_dir + '28*')
# Assign friendly names based on the order found
# IMPORTANT: The order of sensors in device_folders is not fixed.
# If you need specific sensors tied to specific names,
# you'll need to identify their full unique IDs (e.g., '28-00000xxxxx')
# and map them manually. For now, we'll assign them as found.
ds18b20_sensors = {}
if len(device_folders) > 0:
    ds18b20_sensors["ds18b20_temp_1"] = device_folders[0]
#if len(device_folders) > 1:
#    ds18b20_sensors["ds18b20_temp_2"] = device_folders[1]
# Add more entries if you have more than 2 DS18B20s

# MQTT Callbacks 
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
    else:
        print(f"Failed to connect, return code {rc}\n")

def on_disconnect(client, userdata, rc):
    print(f"Disconnected with result code: {rc}")

def on_publish(client, userdata, mid):
    print(f"Message Published with MID: {mid}")

# MQTT client setup
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
client.username_pw_set(THINGSBOARD_EDGE_ACCESS_TOKEN)
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_publish = on_publish

try:
    print(f"Attempting to connect to ThingsBoard Edge at {THINGSBOARD_EDGE_HOST}:{THINGSBOARD_EDGE_PORT}...")
    client.connect(THINGSBOARD_EDGE_HOST, THINGSBOARD_EDGE_PORT, 60)
    client.loop_start() # Start a non-blocking loop for MQTT
except Exception as e:
    print(f"Error connecting to MQTT broker: {e}")
    exit()

# Funcs to read sensor data

def read_ds18b20(device_folder):
    if not device_folder:
        return None
    device_file = device_folder + '/w1_slave'
    try:
        with open(device_file, 'r') as f:
            lines = f.readlines()

        # The DS18B20 can sometimes return 'NO' or CRC errors, retry until 'YES'
        retries = 5
        for _ in range(retries):
            if lines[0].strip()[-3:] == 'YES':
                break
            time.sleep(0.1) # Small delay before retrying read
            with open(device_file, 'r') as f:
                lines = f.readlines()
        else: # If loop completes without break
            print(f"Failed to get 'YES' from DS18B20 after {retries} retries: {device_file}")
            return None

        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            temp_string = lines[1][equals_pos+2:]
            temp_c = float(temp_string) / 1000.0
            return temp_c
    except Exception as e:
        print(f"Error reading DS18B20 from {device_folder}: {e}")
        return None
    return None

def collect_sensor_data():
    data = {}

    # INA260
    try:
        data["voltage_mV"] = ina260.voltage * 1000
        data["voltage_V"] = ina260.voltage
        data["current_mA"] = ina260.current
        data["power_mW"] = ina260.power
        data["resistance_ohm"] = (ina260.voltage * 1000) / ina260.current
    
    except Exception as e:
        print(f"Error reading INA260: {e}")

    # SHT40 (part of ENV IV)
    try:
        data["sht40_temperature_C"] = sht40.temperature
        data["sht40_humidity_percent"] = sht40.relative_humidity
    except Exception as e:
        print(f"Error reading SHT40: {e}")

    # BMP280 (part of ENV IV)
    try:
        data["bmp280_temperature_C"] = bmp280.temperature
        data["pressure_hPa"] = bmp280.pressure
        # You can calculate altitude if needed, but it requires a known sea-level pressure
        # data["altitude_m"] = bmp280.altitude
    except Exception as e:
        print(f"Error reading BMP280: {e}")

    # DS18B20s
    for name, folder in ds18b20_sensors.items():
        temp = read_ds18b20(folder)
        if temp is not None:
            data[name] = temp

    return data

# Main loop
try:
    while True:
        sensor_readings = collect_sensor_data()

        if sensor_readings:
            json_payload = json.dumps(sensor_readings)
            print(f"Publishing: {json_payload}")
            client.publish("v1/devices/me/telemetry", json_payload, qos=1)
        else:
            print("No sensor data collected.")

        time.sleep(5) # Publish every 5 seconds

except KeyboardInterrupt:
    print("Script terminated by user.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
finally:
    client.loop_stop()
    client.disconnect()
    print("MQTT client disconnected.")
    print("Exiting.")

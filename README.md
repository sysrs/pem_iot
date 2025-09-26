
# pem_iot
Remote Monitoring &amp; Control of a Remote PEM Hydrogen Electrolyser System
(This used to be called iot-setup, so look out for any remnants of that name and correct if necessary. Also, this is a work in progress that needs some tidying)


This guide outlines the setup for your IoT project, encompassing a Raspberry Pi 5 edge device, an Azure-hosted Ubuntu server, Docker for containerization, ThingsBoard for IoT data management, Prometheus and Grafana for monitoring, and a reverse SSH tunnel for edge administration.

![Edge Cloud FuelCell Architecture-Design 0 3 drawio (14)](https://github.com/user-attachments/assets/fcb42c3c-ebc6-4221-be09-c7b772281afe)


# Server
## Promethius server

* Taken some from here https://github.com/docker/awesome-compose/blob/master/prometheus-grafana/README.md

Important for Server Prometheus: Given the edge is behind NAT and pushes data, the server-side Prometheus won't be able to scrape the edge directly. The edge Prometheus will use remote_write to push its metrics to the central Prometheus. 

## ThingsBoard CE
https://thingsboard.io/docs/user-guide/install/docker/?ubuntuThingsboardQueue=kafka




# Edge

## The Pi 5
* Raspberry Pi 5 Setup (Edge)
    * Flash OS: Install Raspberry Pi OS (64-bit Lite recommended) onto an SD card.
    * Enable SSH & Wi-Fi (if needed): Configure via raspi-config or manually.
    * Initial Connection: SSH into your Raspberry Pi.
    `ssh pi@YOUR_RPI_IP_ADDRESS`
    * Install Docker and Docker Compose:
    
    ```
    sudo apt update
    sudo apt install -y docker.io docker-compose`
    sudo usermod -aG docker pi # Add your user to the docker group`
    newgrp docker # Apply group changes
    ```
    * test
    ```
    docker run hello-world
    ```
    * Create Persistent Storage Directory:
    
    `mkdir -p /home/<pi_user>/docker`  - be sure to replace <pi_user>

## ThingBoard Edge
Once TB CE is installed on the server use instuctions 
https://thingsboard.io/docs/user-guide/install/edge/docker/?cloudType=on-premise and follow "Guided Installation Using ThingsBoard Server Pre-configured Instructions"

## Node exporter
You'll need to install and run Prometheus Node Exporter on the *host* Raspberry Pi OS (not in a container) to get network telemetry.

```
wget https://github.com/prometheus/node_exporter/releases/download/v1.8.1/node_exporter-1.8.1.linux-arm64.tar.gz # Check for latest version
tar xvfz node_exporter-1.8.1.linux-arm64.tar.gz
cd node_exporter-1.8.1.linux-arm64
./node_exporter
```
* For production, set up Node Exporter as a `systemd` service.
```
sudo useradd --no-create-home --shell /bin/false node_exporter
sudo mv node_exporter /usr/local/bin/
sudo chown node_exporter:node_exporter /usr/local/bin/node_exporter
sudo vim /etc/systemd/system/node_exporter.service
```
```
[Unit]
Description=Node Exporter
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter \
    --web.listen-address=":9100" \
    --collector.filesystem.mount-points-exclude="^/(dev|proc|sys|var/lib/docker/.+)($|/)" \
    --collector.textfile.directory="/var/lib/node_exporter/textfile_collector"

# Restart policy: Restart if the service exits cleanly or with an error
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
```
```
sudo systemctl daemon-reload
sudo systemctl enable node_exporter
sudo systemctl start node_exporter
```
Check status `sudo systemctl status node_exporter`
check again `curl localhost:9100/metrics`

## Custom Python Scripts & Dockerfiles
Note for Camera App:

* You must install `tesseract-ocr` and `libcamera-tools` on the **host Raspberry Pi OS** as well, as the Docker container will rely on the host's camera drivers and potentially the `libcamera-still` executable (or you use `picamera2` Python library, which has its own complexities).
* The `privileged: true` in `docker-compose.yml` for `camera_app` is often necessary for direct hardware access like the camera module.


# Deploy to Raspberry Pi:
SSH into your Raspberry Pi.
Clone your iot-setup repository:
```
git clone https://github.com/sysrs/iot-setup.git
cd iot-setup/edge
```
Build and run Docker Compose:
```
docker compose build
docker compose up -d
```
Make sureNode Exporter on the host OS is running as described above
Configure reverse SSH tunnel if you want

# Gas monitor
```
sudo apt update
sudo apt install python3.11-dev
cd ~/iot-setup/edge/scripts
python3 -m venv venv
source venv/bin/activate
pip install gpiozero paho-mqtt lgpio
sudo usermod -a -G gpio <username>
```
Add the correct `<username>`

## Set it up to run at boot time. 
` sudo nano /etc/systemd/system/gas_monitor.service `

```
[Unit]
Description=Gas Monitor Script
After=network.target

[Service]
User=your_username
WorkingDirectory=/home/your_username/gas_monitor
ExecStart=/home/your_username/gas_monitor/venv/bin/python -u /home/your_username/gas_monitor/gas_monitor.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=gas_monitor

[Install]
WantedBy=multi-user.target
```
change ` User ` and ` WorkingDirectory ` and `ExecStart` to suit your setup. 
We're specifying unbufferedf mode with `-u` so that we can see the debug output when running `sudo journalctl -u gas_monitor.service -f`

```
sudo systemctl daemon-reload
sudo systemctl enable gas_monitor.service
sudo systemctl start gas_monitor.service
```

Check it's running `sudo systemctl status gas_monitor.service`

Check logs `sudo journalctl -u gas_monitor.service -f`


# Pinouts and wiring
```
Raspberry Pi 5 Pinouts

   3V3  (1) (2)  5V    
 GPIO2  (3) (4)  5V    
 GPIO3  (5) (6)  GND   
 GPIO4  (7) (8)  GPIO14
   GND  (9) (10) GPIO15
GPIO17 (11) (12) GPIO18
GPIO27 (13) (14) GND   
GPIO22 (15) (16) GPIO23
   3V3 (17) (18) GPIO24
GPIO10 (19) (20) GND   
 GPIO9 (21) (22) GPIO25
GPIO11 (23) (24) GPIO8 
   GND (25) (26) GPIO7 
 GPIO0 (27) (28) GPIO1 
 GPIO5 (29) (30) GND   
 GPIO6 (31) (32) GPIO12
GPIO13 (33) (34) GND   
GPIO19 (35) (36) GPIO16
GPIO26 (37) (38) GPIO20
   GND (39) (40) GPIO21
```
Pin #   | label     | Used for
---     | ---       | ---
9       | GND       | Milligas counter
11      | GPIO17    | Milligas counter

# The other sensors:

## Connecting Sensors to Raspberry Pi 5 & Posting Data to ThingsBoard Edge
Sensors
* Adafruit INA260 - to measure the voltage, current and power feeding the electrolyser
* Waterproof DS18B20 temperature sensors - reservoir water temp.
* M5Stack ENV IV Unit (SHT40+BMP280) - ambient pressure, humidity and temp.

### Sensor Overview and Pin Connections

**Important Note:** Pull-up resistors are essential for both I2C and 1-Wire communication. For I2C, they are typically integrated into the Raspberry Pi's I2C hardware or the modules themselves. For the DS18B20, you **must** connect your single 4.6kΩ resistor between the shared yellow (Data) wire and the 3.3V line. (wire colours might be differet, check yours.)

### Pin Connections (Raspberry Pi 5) with Sensor Wire Colors

| Sensor                                      | Sensor Wire Color | Pi Pin (BCM) | Pi Pin (Physical) | Description                                            |
| :------------------------------------------ | :---------------- | :----------- | :---------------- | :----------------------------------------------------- |
| **Adafruit INA260 (I2C)** | (Varies, check module) | GPIO 2 (SDA1) | 3                 | I2C Data Line                                          |
|                                             | (Varies, check module) | GPIO 3 (SCL1) | 5                 | I2C Clock Line                                         |
|                                             | (Varies, check module) | 3.3V         | 1                 | Power (3.3V)                                           |
|                                             | (Varies, check module) | GND          | 6                 | Ground                                                 |
| **DS18B20 Sensor 1 (1-Wire)** | **Red** | 3.3V         | 1                 | Power (3.3V) (Shared with Sensor 2)                  |
|                                             | **Yellow** | GPIO 4       | 7                 | 1-Wire Data (Shared with Sensor 2, **requires single 4.6kΩ pull-up resistor to 3.3V**) |
|                                             | **White** | GND          | 9 (or another GND) | Ground (Shared with Sensor 2)                          |
|                                             | **Silver** | GND          | 9 (or another GND) | Shield (optional, connect to GND for noise reduction, shared) |
| **DS18B20 Sensor 2 (1-Wire)** | **Red** | 3.3V         | 1                 | Power (3.3V) (Shared with Sensor 1)                  |
|                                             | **Yellow** | GPIO 4       | 7                 | 1-Wire Data (Shared with Sensor 1, **requires single 4.6kΩ pull-up resistor to 3.3V**) |
|                                             | **White** | GND          | 9 (or another GND) | Ground (Shared with Sensor 1)                          |
|                                             | **Silver** | GND          | 9 (or another GND) | Shield (optional, connect to GND for noise reduction, shared) |
| **ENV IV Unit (SHT40+BMP280) (I2C)** | **Red** | 3.3V         | 1                 | Power (3.3V) (Shared with others)                    |
|                                             | **Black** | GND          | 6                 | Ground (Shared with others)                            |
|                                             | **Yellow** | GPIO 2 (SDA1) | 3                 | I2C Data Line (shared with INA260)                   |
|                                             | **White** | GPIO 3 (SCL1) | 5                 | I2C Clock Line (shared with INA260)                  |

### Software Setup on Raspberry Pi 5

**1. Enable I2C and 1-Wire:**

```bash
sudo raspi-config
```

Navigate to:

  * `3 Interface Options` -\> `I2C` -\> `Yes`
  * `3 Interface Options` -\> `1-Wire` -\> `Yes`

Reboot your Pi.

**2. Update System and Install Basic Tools:**

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3-pip python3-smbus i2c-tools git python3-venv
```

  * `i2c-tools`: Useful for verifying I2C devices (`i2cdetect -y 1`).
  * `python3-venv`: This package is crucial for creating Python virtual environments. You probably already have this installed. 

**3. Create and Activate Virtual Environment:**
* assuming you have pulled the repo to ~/iot-setup ...
```bash
cd ~/iot-setup/edge/scripts

python3 -m venv sensors_venv

source venv/bin/activate
```

**4. Install Python Libraries within Virtual Environment:**

```bash
pip install adafruit-circuitpython-ina260 adafruit-circuitpython-sht4x adafruit-circuitpython-bmp280 paho-mqtt lgpio
```

**5. Verify 1-Wire Devices:**

With 1-Wire enabled and sensors connected, you should see device folders appear.

```bash
ls /sys/bus/w1/devices/
```

You should see two directories starting with `28-`, corresponding to your two DS18B20 sensors (e.g., `28-00000xxxxx` and `28-00000yyyyy`).

### Python Script for Data Collection and MQTT

Script in the repo is `sensors.py`

**Before you run this...:**

  * **ThingsBoard Edge Setup:**
      * An Edge instance running (either on a separate device or locally on the Pi).
      * A Device created in your ThingsBoard Edge, with an "Access Token" generated. You'll use this token as the MQTT username.
      * The IP address or hostname of your ThingsBoard Edge MQTT broker. The default MQTT port is 1883.


* **Edit Placeholders:** **Crucially, replace `YOUR_THINGSBOARD_EDGE_IP_OR_HOSTNAME` and `YOUR_DEVICE_ACCESS_TOKEN`** with your actual ThingsBoard Edge details.
* **Ensure Virtual Environment is Active:** Make sure you've run `source venv_sensors/bin/activate` in your terminal.
4.  **Run the script:**
    ```bash
    python sensors.py
    ```
    *Note: You can just use `python` now instead of `python3` because the virtual environment ensures you're using the correct Python 3 executable.*
5.  **Check ThingsBoard Edge:** Go to your ThingsBoard Edge dashboard, navigate to your device, and check the "Latest Telemetry" tab. You should see the incoming data.

### Notes and TODO:

  * **Autostart:** To make this script run automatically on boot, you can use `cron` or `systemd`. If using `cron`, ensure you specify the full path to your Python executable within the virtual environment:
    ```bash
    # Example for cron - use 'crontab -e'
    @reboot /home/pi/sensor_project/venv/bin/python /home/pi/sensor_project/sensor_to_thingsboard.py &
    ```
    Using `systemd` is often more robust for services that need to be managed and restarted.
  * For the scitps to control the `RND 320-KA3005P `power supply The host Python script CAN directly connect to localhost:1883 (or 127.0.0.1:1883) to communicate with the ThingsBoard Edge MQTT broker. This greatly simplifies the communication strategy between your host Python script and ThingsBoard Edge. As such, we won't need an additional MQTT broker on the host or complex networking configurations. So, the communication flow will be:
```
ThingsBoard CE (Azure) --> ThingsBoard Edge (Docker on Pi5): Standard ThingsBoard sync/RPC.

ThingsBoard Edge (Docker) <--> Host Python Script: Via MQTT on localhost:1883.
```

## Voltage, current and power sensor
* https://learn.adafruit.com/assets/77678

## Environment sensor

## Water temperature sensor


# TODO
* reverse SSH for remote admin top Pi
* Fail2ban
* CCZE
* VIM``
* DNS




# Controlling the RND 320-KA3005P power supply

Aim is to control a USB-connected power supply (RND 320-KA3005P) on a Raspberry Pi 5 via ThingsBoard, allowing for dynamic power profiles to be applied remotely from a ThingsBoard CE dashboard.

### Baseline setup

* **Hardware:** Raspberry Pi 5.
* **Operating System:** Raspberry Pi OS (Host OS).
* **Docker Containers (on Pi5):**
    * ThingsBoard Edge
    * PostgreSQL
    * Prometheus
    * Node Exporter
* **IoT Platform - Cloud:** ThingsBoard Community Edition (TB CE) running on Azure, syncing with TB Edge.
* **Local Sensors:** Various sensors connected via GPIO pins.
* **Sensor Data Acquisition:** Python scripts (running directly on the **Host OS**) read sensor data and publish it to ThingsBoard Edge via MQTT (connecting to `localhost:1883`).
* **Data Visualization:** Dashboards on ThingsBoard CE for monitoring.

### New Components & Their Integration

Here's a breakdown of the elements and how they'll fit into the system:

| Component | Details | Integration Method |
| :- | :- | :- |
| **Power Supply** | RND 320-KA3005P (USB controlled)  | Connects directly to the Pi 5's USB port. |
| **Control Library** | `ka3005p` Python library (from PyPI) | Installed in a dedicated Python virtual environment on the **Raspberry Pi 5 Host OS**. |
| **Control Logic** | Custom Python script to control the PSU using `ka3005p` | Runs directly on the **Raspberry Pi 5 Host OS**. Will act as an MQTT client. |
| **Communication (Pi)** | Between **Host Python scripts** (sensors & PSU) and ThingsBoard Edge Docker container. | **Direct MQTT communication:** Host Python scripts connect to `localhost:1883` (ThingsBoard Edge's exposed MQTT port). |
| **Control Flow (Cloud)** | From ThingsBoard CE to the Pi's power supply. | **RPC (Remote Procedure Call):** ThingsBoard CE dashboard sends an RPC command to the associated device on ThingsBoard Edge. |
| **Power Profile Data** | Voltage/Current values changing over time (e.g., CSV, JSON).               | **Proposed:** Stored as a JSON array Shared Attribute on the ThingsBoard device. This attribute will be read by the Host Python script. |
| **Profile Trigger** | How to initiate a power profile run. | **Manual Trigger:** Initiated from a ThingsBoard CE dashboard widget (e.g., a button sending an RPC). |
| **Monitoring PS Status** | Actual voltage/current of the power supply. | Already being collected as telemetry (by existing sensor script on host).                                                                 |

---

### Step-by-Step Plan Summary

1.  **Identify USB Device Path:** Find the persistent `/dev/serial/by-id/` path for your RND 320-KA3005P on the Raspberry Pi 5. (Critical first step for host Python control).
   ```bash
ls -l /dev/serial/by-id/
total 0
lrwxrwxrwx 1 root root 13 Jul 29 13:25 usb-Nuvoton_USB_Virtual_COM_000962640452-if00 -> ../../ttyACM0
```
The persistent USB device path for this particular RND 320-KA3005P power supply is:
`/dev/serial/by-id/usb-Nuvoton_USB_Virtual_COM_000962640452-if00`
Using this path in the Python script will ensure that we always connect to the correct power supply, regardless of whether it shows up as ttyACM0, ttyACM1, or another number after reboots or replugs. Make sure you replace this in your setup as needed. 

2.  **Prepare Host Python Environment:** Create a virtual environment on the Pi 5 host, install `ka3005p` and `pyserial`. Ensure the user running the script has `dialout` group permissions.

  **Create a Virtual Environment:**

```bash
cd ~/power_supply_controller
python3 -m venv venv           # Create the virtual environment
source venv/bin/activate       # Activate the virtual environment
```

  **Install `ka3005p` and `pyserial`:**

```bash
pip install ka3005p pyserial
```

  **Grant Permissions:**
    Add your current user (e.g., `pi` if you're logged in as `pi`) to the `dialout` group:

```bash
sudo usermod -a -G dialout $USER # Or replace $USER with 'pi' if appropriate
```

    **Important:** You must log out of your SSH session or terminal and log back in for this group membership change to take effect.

  **Create and Run the Test Script (`test_psu.py`):**
    Open a new file:

```bash
vim ~/power_supply_controller/test_psu.py
```

**Once all testing is done, then use the code from this repo, and use the below to set it up as a service so that it starts when the Pi boots up....
```bash
sudo vim /etc/systemd/system/ka3005p_controller.service
```
```Ini, TOML
[Unit]
Description=KA3005P Power Supply Controller Script
After=network.target

[Service]
# IMPORTANT: Replace 'your_username' with your actual username (e.g., 'pi')
User=your_username
WorkingDirectory=/home/your_username/iot-setup/edge/scripts
# Replace 'your_username' below to point to your virtual environment's python executable
ExecStart=/home/your_username/iot-setup/edge/scripts/psu_env/bin/python -u KA3005P_controller.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ka3005p_controller

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
```
```bash
sudo systemctl enable ka3005p_controller.service
```
```bash
sudo systemctl start ka3005p_controller.service
```
Check the status:
```bash
sudo systemctl status ka3005p_controller.service
```
View real-time logs (unbuffered output):
```bash
sudo journalctl -u ka3005p_controller.service -f
```







Observe your power supply to see if it responds by setting the voltage/current and turning the output on and off. This confirms successful communication with the hardware from your host Python environment.

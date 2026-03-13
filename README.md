# bme680-logger

Log data from an I²C-connected BME680 sensor every 5 minutes, display it on an OLED screen and serve a simple web interface.

## Features

| # | Feature |
|---|---------|
| F1 | Sensor data logged every 5 minutes to a daily CSV file |
| F2 | Web interface shows current readings and a 7-day history chart |
| F3 | Raw CSV download from the web interface |
| F4 | A new log file is created automatically each day |
| F5 | Runs as a `systemd` service with automatic restart on failure |
| F6 | OLED (I²C, address `0x3C`) shows current temperature, humidity, pressure and gas resistance |
| F7 | Web interface toggle to turn the OLED on or off |
| F8 | OLED is only active during configurable daylight hours (default 08:00–22:00) |

## Hardware

* Raspberry Pi (any model with I²C)
* Pimoroni BME680 breakout (I²C address `0x76` primary)
* 128×64 SSD1306 OLED display (I²C address `0x3C`)

## Prerequisites

The required Python libraries are bundled in the Pimoroni virtualenv:

```
~/.virtualenvs/pimoroni/
```

Enable I²C on the Pi:

```bash
sudo raspi-config  # Interface Options → I2C → Enable
```

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/doofmars/bme680-logger.git /home/pi/bme680-logger
cd /home/pi/bme680-logger

# 2. Install Flask into the Pimoroni venv (other libs are already present)
~/.virtualenvs/pimoroni/bin/pip install Flask>=2.3

# 3. Install the systemd service
sudo cp bme680-logger.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bme680-logger
sudo systemctl start bme680-logger
```

## Configuration

Edit `config.ini` before starting the service:

```ini
[logging]
log_dir = logs            # Directory for daily CSV files
interval_seconds = 300    # Logging interval (seconds)

[display]
daylight_start = 8        # Hour the OLED turns on  (0-23)
daylight_end   = 22       # Hour the OLED turns off (0-23)

[web]
host = 0.0.0.0
port = 8080
```

## Usage

Open `http://<raspberry-pi-ip>:8080` in a browser.

| Path | Description |
|------|-------------|
| `/` | Dashboard – current readings, 7-day chart, display toggle |
| `/download` | Download today's CSV file |
| `/api/current` | JSON – latest sensor reading |
| `/api/history?days=7` | JSON – last *N* days of readings |
| `/api/display` | GET / POST – query or set display state (`{"enabled": true/false}`) |

## Log file format

Files are stored as `<log_dir>/bme680_YYYY-MM-DD.csv`:

```
timestamp,temperature,pressure,humidity,gas_resistance
2024-06-01T08:00:00,22.35,1013.25,54.12,45231.0
```

## Running manually

```bash
~/.virtualenvs/pimoroni/bin/python main.py
```

## Running on port 80

By default the service binds to port **8080**. To use the standard HTTP port 80 without running as root, two approaches are recommended:

### Option A – authbind

```bash
sudo apt-get install authbind
sudo touch /etc/authbind/byport/80
sudo chmod 500 /etc/authbind/byport/80
sudo chown pi /etc/authbind/byport/80
```

Update `bme680-logger.service` to use authbind:

```ini
ExecStart=authbind --deep /home/pi/.virtualenvs/pimoroni/bin/python main.py
```

And set `port = 80` in `config.ini`.

### Option B – systemd socket capabilities

Add `AmbientCapabilities` to the `[Service]` section of `bme680-logger.service`:

```ini
AmbientCapabilities=CAP_NET_BIND_SERVICE
```

Then set `port = 80` in `config.ini` and reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart bme680-logger
```



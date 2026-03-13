#!/usr/bin/env python3
"""
BME680 Logger Service
---------------------
* Reads a BME680 sensor every ``interval_seconds`` (default 5 min).
* Appends readings to a daily CSV file (F1, F4).
* Serves a small Flask web-UI that shows current values, a history chart and
  a raw-data download link (F2, F3).
* Drives a luma.oled OLED display; supports on/off toggle and a daylight
  window (F6, F7, F8).
* Designed to run as a systemd service (F5).
"""

import configparser
import csv
import glob
import logging
import os
import threading
import time
from datetime import date, datetime

from flask import Flask, abort, jsonify, render_template, request, send_file

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(os.path.dirname(__file__), "config.ini"))

LOG_DIR = _cfg.get("logging", "log_dir", fallback="logs")
LOG_INTERVAL = _cfg.getint("logging", "interval_seconds", fallback=300)
DAYLIGHT_START = _cfg.getint("display", "daylight_start", fallback=8)
DAYLIGHT_END = _cfg.getint("display", "daylight_end", fallback=22)
WEB_HOST = _cfg.get("web", "host", fallback="0.0.0.0")
WEB_PORT = _cfg.getint("web", "port", fallback=8080)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardware initialisation (graceful fallback when hardware is absent)
# ---------------------------------------------------------------------------

# BME680 sensor
try:
    import bme680 as _bme680_mod

    _sensor = _bme680_mod.BME680(_bme680_mod.I2C_ADDR_PRIMARY)
    _sensor.set_humidity_oversample(_bme680_mod.OS_2X)
    _sensor.set_pressure_oversample(_bme680_mod.OS_4X)
    _sensor.set_temperature_oversample(_bme680_mod.OS_8X)
    _sensor.set_filter(_bme680_mod.FILTER_SIZE_3)
    _sensor.set_gas_status(_bme680_mod.ENABLE_GAS_MEAS)
    _sensor.set_gas_heater_temperature(320)
    _sensor.set_gas_heater_duration(150)
    _sensor.select_gas_heater_profile(0)
    SENSOR_OK = True
    log.info("BME680 sensor initialised")
except Exception as _e:
    _sensor = None
    SENSOR_OK = False
    log.warning("BME680 sensor not available: %s", _e)

# OLED display
try:
    from luma.core.interface.serial import i2c as _luma_i2c
    from luma.core.render import canvas as _luma_canvas
    from luma.oled.device import ssd1306 as _ssd1306

    _serial = _luma_i2c(port=0, address=0x3C)
    _display = _ssd1306(_serial)
    DISPLAY_OK = True
    log.info("OLED display initialised")
except Exception as _e:
    _display = None
    DISPLAY_OK = False
    log.warning("OLED display not available: %s", _e)

# Font for OLED – prefer a readable TrueType font, fall back to PIL default
_OLED_FONT = None
try:
    from PIL import ImageFont as _ImageFont

    try:
        _OLED_FONT = _ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12
        )
    except Exception:
        _OLED_FONT = _ImageFont.load_default()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_latest: dict = {}
_display_enabled: bool = True
_display_lock = threading.Lock()

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

CSV_FIELDS = ["timestamp", "temperature", "pressure", "humidity", "gas_resistance"]


def _log_path() -> str:
    """Return the path of today's CSV log file, creating the directory if needed."""
    os.makedirs(LOG_DIR, exist_ok=True)
    return os.path.join(LOG_DIR, f"bme680_{date.today():%Y-%m-%d}.csv")


def _append_row(data: dict) -> None:
    path = _log_path()
    write_header = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(data)


# ---------------------------------------------------------------------------
# Sensor reading
# ---------------------------------------------------------------------------


def _read_sensor():
    """Return a dict with sensor readings, or None if unavailable."""
    if not SENSOR_OK:
        return None
    if _sensor.get_sensor_data():
        gas = (
            round(_sensor.data.gas_resistance, 0)
            if _sensor.data.heat_stable
            else None
        )
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "temperature": round(_sensor.data.temperature, 2),
            "pressure": round(_sensor.data.pressure, 2),
            "humidity": round(_sensor.data.humidity, 2),
            "gas_resistance": gas,
        }
    return None


# ---------------------------------------------------------------------------
# OLED display
# ---------------------------------------------------------------------------


def _refresh_display(data: dict) -> None:
    """Render current readings on the OLED or hide it when appropriate."""
    if not DISPLAY_OK:
        return
    with _display_lock:
        hour = datetime.now().hour
        if not _display_enabled or not (DAYLIGHT_START <= hour < DAYLIGHT_END):
            _display.hide()
            return
        _display.show()
        font = _OLED_FONT  # may be None if PIL unavailable
        with _luma_canvas(_display) as draw:
            draw.text((0, 0),  f"Temp:  {data['temperature']:.1f} \u00b0C", fill="white", font=font)
            draw.text((0, 14), f"Hum:   {data['humidity']:.1f} %",          fill="white", font=font)
            draw.text((0, 28), f"Press: {data['pressure']:.1f} hPa",        fill="white", font=font)
            gas = data.get("gas_resistance")
            if gas is not None:
                draw.text((0, 42), f"Gas:   {int(gas)} \u03a9",             fill="white", font=font)


# ---------------------------------------------------------------------------
# Background sensor loop
# ---------------------------------------------------------------------------


def _sensor_loop() -> None:
    global _latest
    # Read immediately on startup; retry every second until data is available
    while not _latest:
        try:
            data = _read_sensor()
            if data:
                _latest = data
                _append_row(data)
                _refresh_display(data)
                log.info("Initial read: %s", data)
            else:
                log.debug("Waiting for initial sensor data…")
                time.sleep(1)
        except Exception as exc:
            log.error("Startup sensor read error: %s", exc)
            time.sleep(1)

    # Subsequent reads at the configured interval
    while True:
        time.sleep(LOG_INTERVAL)
        try:
            data = _read_sensor()
            if data:
                _latest = data
                _append_row(data)
                _refresh_display(data)
                log.info("Logged: %s", data)
            else:
                log.debug("No sensor data available")
        except Exception as exc:
            log.error("Sensor loop error: %s", exc)


# ---------------------------------------------------------------------------
# Flask web application
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/")
def index():
    return render_template(
        "index.html",
        data=_latest,
        display_enabled=_display_enabled,
    )


@app.route("/api/current")
def api_current():
    return jsonify(_latest)


@app.route("/api/history")
def api_history():
    """Return up to *days* days of CSV rows as JSON (newest last)."""
    days = request.args.get("days", 7, type=int)
    rows = []
    pattern = os.path.join(LOG_DIR, "bme680_*.csv")
    for path in sorted(glob.glob(pattern))[-days:]:
        try:
            with open(path, newline="") as fh:
                rows.extend(list(csv.DictReader(fh)))
        except OSError as exc:
            log.warning("Cannot read %s: %s", path, exc)
    return jsonify(rows)


@app.route("/download")
def download():
    """Serve today's CSV file as a download."""
    path = _log_path()
    if not os.path.exists(path):
        abort(404, description="No data logged yet for today.")
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@app.route("/api/display", methods=["GET"])
def display_get():
    return jsonify({"enabled": _display_enabled})


@app.route("/api/display", methods=["POST"])
def display_post():
    global _display_enabled
    body = request.get_json(force=True, silent=True) or {}
    _display_enabled = bool(body.get("enabled", _display_enabled))
    if not _display_enabled and DISPLAY_OK:
        # Immediately hide the display when turned off
        with _display_lock:
            _display.hide()
    elif _display_enabled and DISPLAY_OK and _latest:
        # Immediately refresh the display when turned on
        _refresh_display(_latest)
    log.info("Display enabled set to: %s", _display_enabled)
    return jsonify({"enabled": _display_enabled})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)

    sensor_thread = threading.Thread(target=_sensor_loop, daemon=True, name="sensor")
    sensor_thread.start()

    log.info("Starting web server on %s:%s", WEB_HOST, WEB_PORT)
    app.run(host=WEB_HOST, port=WEB_PORT, use_reloader=False)

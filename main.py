#!/usr/bin/env python3
"""
BME688 Logger Service
---------------------
* Reads a BME688 sensor every ``read_interval_seconds`` (default 5 s) and
  refreshes the OLED display with the latest values.
* Appends readings (including IAQ) to a daily CSV file every
  ``interval_seconds`` (default 5 min) (F1, F4).
* Serves a Flask web-UI that shows current values, a history chart and
  a raw-data download link (F2, F3).
* Drives a luma.oled OLED display with configurable view modes including
  an IAQ cycling option (F6, F7, F8, F9).
* Designed to run as a systemd service (F5).
"""

import logging
import os
import threading
import time

from src import sensor, display, csv_logger
from src.config import LOG_DIR, READ_INTERVAL, LOG_INTERVAL, WEB_HOST, WEB_PORT
from src.web import app

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
# Background sensor loop
# ---------------------------------------------------------------------------


def _sensor_loop():
    # Get first reading immediately; retry every second until data arrives
    while not sensor.get_latest():
        try:
            data = sensor.read_sensor()
            if data:
                sensor.set_latest(data)
                csv_logger.append_row(LOG_DIR, data)
                display.refresh_display(data)
                log.info("Initial read: %s", data)
            else:
                log.debug("Waiting for initial sensor data\u2026")
                time.sleep(1)
        except Exception as exc:
            log.error("Startup sensor read error: %s", exc)
            time.sleep(1)

    # Collect gas burn-in data for IAQ calibration (~50 s, runs in background)
    sensor.collect_burn_in()

    # Read the sensor every READ_INTERVAL seconds; write to CSV every LOG_INTERVAL seconds
    last_log_time = time.monotonic()
    while True:
        time.sleep(READ_INTERVAL)
        try:
            data = sensor.read_sensor()
            if data:
                sensor.set_latest(data)
                display.refresh_display(data)
                now = time.monotonic()
                if now - last_log_time >= LOG_INTERVAL:
                    csv_logger.append_row(LOG_DIR, data)
                    log.info("Logged: %s", data)
                    last_log_time = now
                else:
                    log.debug("Read: %s", data)
            else:
                log.debug("No sensor data available")
        except Exception as exc:
            log.error("Sensor loop error: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)

    sensor_thread = threading.Thread(target=_sensor_loop, daemon=True, name="sensor")
    sensor_thread.start()

    log.info("Starting web server on %s:%s", WEB_HOST, WEB_PORT)
    app.run(host=WEB_HOST, port=WEB_PORT, use_reloader=False)

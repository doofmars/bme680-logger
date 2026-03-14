"""CSV logging helpers for daily BME688 sensor data files."""

import csv
import logging
import os
from datetime import date

log = logging.getLogger(__name__)

CSV_FIELDS = [
    "timestamp",
    "temperature",
    "pressure",
    "humidity",
    "gas_resistance",
    "iaq",
]


def log_path(log_dir):
    """Return the path of today's CSV log file, creating the directory if needed."""
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"bme688_{date.today():%Y-%m-%d}.csv")


def append_row(log_dir, data):
    """Append a sensor reading *dict* to today's CSV log file."""
    path = log_path(log_dir)
    write_header = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(data)

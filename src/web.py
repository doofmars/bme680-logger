"""Flask web application for the BME688 Logger."""

import csv
import glob
import logging
import os

from flask import Flask, abort, jsonify, render_template, request, send_file

import display
import sensor
from config import LOG_DIR
from csv_logger import log_path

log = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def index():
    return render_template(
        "index.html",
        data=sensor.get_latest(),
        display_enabled=display.is_enabled(),
    )


@app.route("/api/current")
def api_current():
    return jsonify(sensor.get_latest())


@app.route("/api/history")
def api_history():
    """Return up to *days* days of CSV rows as JSON (newest last)."""
    days = request.args.get("days", 7, type=int)
    rows = []
    pattern = os.path.join(LOG_DIR, "bme688_*.csv")
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
    path = os.path.abspath(log_path(LOG_DIR))
    if not os.path.exists(path):
        abort(404, description="No data logged yet for today.")
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@app.route("/api/display", methods=["GET"])
def display_get():
    return jsonify({"enabled": display.is_enabled()})


@app.route("/api/display", methods=["POST"])
def display_post():
    body = request.get_json(force=True, silent=True) or {}
    enabled = bool(body.get("enabled", display.is_enabled()))
    display.set_enabled(enabled)
    if not enabled and display.get_display_ok():
        with display.get_display_lock():
            display.get_display().hide()
    elif enabled and display.get_display_ok() and sensor.get_latest():
        display.refresh_display(sensor.get_latest())
    log.info("Display enabled set to: %s", enabled)
    return jsonify({"enabled": display.is_enabled()})

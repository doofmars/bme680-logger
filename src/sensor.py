"""BME688 sensor initialisation and reading with simplified IAQ calculation.

The BME688 is the successor to the BME680, offering the same temperature,
pressure, humidity and gas-resistance measurements plus improved gas scanning.
The Pimoroni ``bme680`` Python library is compatible with both devices.

IAQ is approximated from the gas-resistance baseline and the deviation of
relative humidity from the ideal 40 % RH point.  A 50-sample burn-in phase
is required before the gas-resistance baseline is stable enough to produce
meaningful IAQ scores.
"""

import logging
import time
from datetime import datetime

log = logging.getLogger(__name__)

_BURN_IN_COUNT = 50  # readings collected before IAQ baseline is locked in

# ---------------------------------------------------------------------------
# Sensor initialisation (graceful fallback when hardware is absent)
# ---------------------------------------------------------------------------

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
    log.info("BME688 sensor initialised")
except Exception as _e:
    _sensor = None
    SENSOR_OK = False
    log.warning("BME688 sensor not available: %s", _e)

# ---------------------------------------------------------------------------
# IAQ calibration state
# ---------------------------------------------------------------------------

_gas_baseline = None
_burn_in_data = []
_iaq_ready = False
_latest = {}


def collect_burn_in():
    """Collect gas burn-in readings to calibrate the IAQ baseline.

    Blocks for approximately *_BURN_IN_COUNT* seconds while sampling the gas
    sensor once per second.  When the sensor is unavailable the function
    returns immediately.
    """
    global _gas_baseline, _burn_in_data, _iaq_ready
    if not SENSOR_OK:
        return
    log.info("Collecting IAQ burn-in data (%d readings)...", _BURN_IN_COUNT)
    while len(_burn_in_data) < _BURN_IN_COUNT:
        if _sensor.get_sensor_data() and _sensor.data.heat_stable:
            _burn_in_data.append(_sensor.data.gas_resistance)
        time.sleep(1)
    _gas_baseline = sum(_burn_in_data[-10:]) / 10.0
    _iaq_ready = True
    log.info("IAQ burn-in complete. Gas baseline: %.0f \u03a9", _gas_baseline)


# ---------------------------------------------------------------------------
# IAQ helpers
# ---------------------------------------------------------------------------


def _calculate_iaq(gas_resistance, humidity):
    """Return a simplified IAQ score (0–500, lower is better), or None.

    The algorithm is adapted from the Bosch reference implementation:
    https://github.com/pimoroni/bme680-python/blob/main/examples/indoor-air-quality.py

    * Humidity contributes 25 % of the score (ideal 40 % RH).
    * Gas resistance contributes 75 % of the score (higher = cleaner air).
    The combined 0–100 score is then mapped to the 0–500 AQI-style range.
    """
    if not _iaq_ready or _gas_baseline is None or gas_resistance is None:
        return None
    # Humidity: linearly tapers from 25 at 40 % RH down to 0 at ≤0 % or ≥80 % RH;
    # clamped so values outside 0–80 % do not produce negative contributions.
    hum_score = 25.0 * (1.0 - abs(humidity - 40.0) / 40.0)
    hum_score = max(0.0, min(hum_score, 25.0))
    gas_score = 75.0 * min(gas_resistance / _gas_baseline, 1.0)
    return round((100.0 - (hum_score + gas_score)) * 5.0)


def iaq_label(iaq):
    """Return a human-readable quality category for an IAQ score."""
    if iaq is None:
        return "Warming up"
    if iaq <= 50:
        return "Good"
    if iaq <= 100:
        return "Moderate"
    if iaq <= 150:
        return "Unhealthy (sensitive)"
    if iaq <= 200:
        return "Unhealthy"
    if iaq <= 300:
        return "Very unhealthy"
    return "Hazardous"


# ---------------------------------------------------------------------------
# Sensor reading
# ---------------------------------------------------------------------------


def read_sensor():
    """Return a dict with all sensor readings, or None if unavailable."""
    if not SENSOR_OK:
        return None
    if _sensor.get_sensor_data():
        gas = (
            round(_sensor.data.gas_resistance, 0)
            if _sensor.data.heat_stable
            else None
        )
        iaq = _calculate_iaq(gas, _sensor.data.humidity)
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "temperature": round(_sensor.data.temperature, 2),
            "pressure": round(_sensor.data.pressure, 2),
            "humidity": round(_sensor.data.humidity, 2),
            "gas_resistance": gas,
            "iaq": iaq,
        }
    return None


# ---------------------------------------------------------------------------
# Shared latest reading
# ---------------------------------------------------------------------------


def get_latest():
    """Return a copy of the most recent sensor reading dict (may be empty on startup)."""
    return _latest.copy()


def set_latest(data):
    """Update the shared latest reading."""
    global _latest
    _latest = data

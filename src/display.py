"""OLED display management with configurable view modes.

Supported ``display_mode`` values (set in ``config.ini``):

* ``temp_hum`` – show temperature and humidity on every refresh.
* ``iaq``      – show the IAQ score and quality label on every refresh.
* ``cycle``    – alternate between the two views every minute.
"""

import logging
import threading
from datetime import datetime

from config import DAYLIGHT_END, DAYLIGHT_START, DISPLAY_MODE, FONT_SIZE
from sensor import iaq_label

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Display initialisation (graceful fallback when hardware is absent)
# ---------------------------------------------------------------------------

try:
    from luma.core.interface.serial import i2c as _luma_i2c
    from luma.core.render import canvas as _luma_canvas
    from luma.oled.device import ssd1316 as _ssd1316

    _serial = _luma_i2c(port=0, address=0x3C)
    _display = _ssd1316(_serial)
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
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", FONT_SIZE
        )
    except Exception:
        _OLED_FONT = _ImageFont.load_default()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Shared display state
# ---------------------------------------------------------------------------

_display_enabled = True
_display_lock = threading.Lock()


def is_enabled():
    """Return whether the display is currently enabled."""
    return _display_enabled


def set_enabled(enabled):
    """Enable or disable the display."""
    global _display_enabled
    _display_enabled = enabled


def get_display_ok():
    """Return whether the OLED hardware was successfully initialised."""
    return DISPLAY_OK


def get_display():
    """Return the luma.oled device, or None if unavailable."""
    return _display


def get_display_lock():
    """Return the threading lock that guards display access."""
    return _display_lock


# ---------------------------------------------------------------------------
# View selection
# ---------------------------------------------------------------------------


def _current_view():
    """Return ``'temp_hum'`` or ``'iaq'`` based on config and current time.

    In ``cycle`` mode the view switches every minute (even minute → temp/hum,
    odd minute → IAQ).
    """
    if DISPLAY_MODE == "temp_hum":
        return "temp_hum"
    if DISPLAY_MODE == "iaq":
        return "iaq"
    # cycle: even minute = temp_hum, odd minute = iaq
    return "iaq" if (datetime.now().minute % 2 == 1) else "temp_hum"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def refresh_display(data):
    """Render current readings on the OLED or hide it when appropriate."""
    if not DISPLAY_OK:
        return
    with _display_lock:
        hour = datetime.now().hour
        view = _current_view()
        if not _display_enabled or not (DAYLIGHT_START <= hour < DAYLIGHT_END):
            _display.hide()
            return
        _display.show()
        font = _OLED_FONT
        with _luma_canvas(_display) as draw:
            if view == "iaq":
                iaq_val = data.get("iaq")
                label = iaq_label(iaq_val)
                draw.text(
                    (0, 0),
                    f"IAQ:  {iaq_val if iaq_val is not None else '\u2013'}",
                    fill="white",
                    font=font,
                )
                draw.text(
                    (0, FONT_SIZE),
                    label[:20],
                    fill="white",
                    font=font,
                )
            else:
                now = datetime.now().isoformat()
                draw.text(
                    (0, 0),
                    f"Temp: {data['temperature']:.1f} \u00b0C {now[11:13]}",
                    fill="white",
                    font=font,
                )
                draw.text(
                    (0, FONT_SIZE),
                    f"Hum:  {data['humidity']:.1f} %  {now[14:16]}",
                    fill="white",
                    font=font,
                )

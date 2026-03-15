"""Application configuration loaded from config.ini."""
import configparser
import os

_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(os.path.dirname(__file__), "..", "config.ini"))

LOG_DIR = _cfg.get("logging", "log_dir", fallback="logs")
READ_INTERVAL = _cfg.getint("logging", "read_interval_seconds", fallback=5)
LOG_INTERVAL = _cfg.getint("logging", "interval_seconds", fallback=300)
DAYLIGHT_START = _cfg.getint("display", "daylight_start", fallback=8)
DAYLIGHT_END = _cfg.getint("display", "daylight_end", fallback=22)
# display_mode: temp_hum | iaq | cycle
DISPLAY_MODE = _cfg.get("display", "display_mode", fallback="cycle")
WEB_HOST = _cfg.get("web", "host", fallback="0.0.0.0")
WEB_PORT = _cfg.getint("web", "port", fallback=8080)
FONT_SIZE = 15

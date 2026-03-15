"""Application configuration loaded from config.ini."""
import configparser
import os

_cfg = configparser.ConfigParser()
_cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.ini")
if os.path.exists(_cfg_path):
    _cfg.read(_cfg_path)
else:
    raise FileNotFoundError(f"Config.ini not found in {_cfg_path}")

LOG_DIR = _cfg.get("logging", "log_dir")
READ_INTERVAL = _cfg.getint("logging", "read_interval_seconds")
LOG_INTERVAL = _cfg.getint("logging", "interval_seconds")
DAYLIGHT_START = _cfg.getint("display", "daylight_start")
DAYLIGHT_END = _cfg.getint("display", "daylight_end")
# display_mode: temp_hum | iaq | cycle
DISPLAY_MODE = _cfg.get("display", "display_mode")
WEB_HOST = _cfg.get("web", "host")
WEB_PORT = _cfg.getint("web", "port")
FONT_SIZE = 15

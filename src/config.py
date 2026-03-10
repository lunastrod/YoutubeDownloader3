import json
import logger as log
import os
import sys


def _get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CONFIG_PATH = os.path.join(_get_base_dir(), "config", "config.json")

DEFAULTS = {
    "output_dir": os.path.expanduser("~/Downloads"),
    "embed_lyrics": True,
    "verbose": False,
    "browser": None,
}


def load() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                log.logger.log_verbose(f"Config loaded from {CONFIG_PATH}: {data}")
                return {**DEFAULTS, **data}
        except Exception:
            log.logger.warning(f"Could not load config from {CONFIG_PATH}.")
            pass
    log.logger.warning("Could not load config, using defaults.")
    return DEFAULTS.copy()


def save(config: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            log.logger.log_verbose(f"Config saved to {CONFIG_PATH}: {config}")
    except Exception:
        log.logger.error(f"Could not save config to {CONFIG_PATH}.")
        pass
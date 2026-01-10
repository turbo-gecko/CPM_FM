import json
import os
from .defaults import SERIAL_DEFAULTS, GENERAL_DEFAULTS

CONFIG_FILE = os.path.expanduser("~/.cpm_fm_config.json")

def load_settings():
    if not os.path.exists(CONFIG_FILE):
        return {"serial": SERIAL_DEFAULTS, "general": GENERAL_DEFAULTS}
    
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_settings(settings):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

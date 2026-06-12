import json
import os
from typing import Any


class ConfigHandler:
    """
    Handles loading and saving of configuration files for the CP/M File Manager.
    Supports both the simple serial_settings.json and the structured settings_a.json formats.
    """

    @staticmethod
    def load_json(filepath: str) -> dict[str, Any]:
        """Loads a JSON file and returns its content as a dictionary."""
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error loading config file {filepath}: {e}")
            return {}

    @staticmethod
    def save_json(filepath: str, data: dict[str, Any]) -> bool:
        """Saves a dictionary to a JSON file."""
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=4)
            return True
        except OSError as e:
            print(f"Error saving config file {filepath}: {e}")
            return False


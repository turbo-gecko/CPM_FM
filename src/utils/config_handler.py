import json
import os
from typing import Any, Dict

class ConfigHandler:
    """
    Handles loading and saving of configuration files for the CP/M File Manager.
    Supports both the simple serial_settings.json and the structured settings_a.json formats.
    """
    
    @staticmethod
    def load_json(filepath: str) -> Dict[str, Any]:
        """Loads a JSON file and returns its content as a dictionary."""
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading config file {filepath}: {e}")
            return {}

    @staticmethod
    def save_json(filepath: str, data: Dict[str, Any]) -> bool:
        """Saves a dictionary to a JSON file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
            return True
        except IOError as e:
            print(f"Error saving config file {filepath}: {e}")
            return False

    @staticmethod
    def validate_serial_settings(settings: Dict[str, Any]) -> bool:
        """
        Basic validation for serial settings.
        Checks for required keys based on the design document.
        """
        required_keys = ['terminal_port', 'transport_port', 'speed']
        # Support both flat and nested structures
        data = settings.get('serial', settings) if 'serial' in settings else settings
        return all(key in data for key in required_keys)

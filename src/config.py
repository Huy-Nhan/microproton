import os
import json

class SettingsManager:
    SETTINGS_DIR = os.path.expanduser("~/.config/micro-proton")
    SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

    @classmethod
    def get_settings(cls):
        try:
            if os.path.exists(cls.SETTINGS_FILE):
                with open(cls.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    @classmethod
    def save_settings(cls, settings_dict):
        try:
            os.makedirs(cls.SETTINGS_DIR, exist_ok=True)
            data = cls.get_settings()
            data.update(settings_dict)
            with open(cls.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving global settings: {e}")

    @classmethod
    def get_default_proton(cls):
        return cls.get_settings().get("default_proton", "")

    @classmethod
    def save_default_proton(cls, proton_name):
        cls.save_settings({"default_proton": proton_name})

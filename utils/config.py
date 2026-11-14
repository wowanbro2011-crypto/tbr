# utils/config.py
import os
import sys
import shutil
import configparser
from utils.helpers import APP_DATA_DIR

if getattr(sys, 'frozen', False):
    OLD_BASE_DIR = os.path.dirname(sys.executable)
else:
    OLD_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(APP_DATA_DIR, 'config.ini')
OLD_CONFIG_FILE = os.path.join(OLD_BASE_DIR, 'config.ini')

class AppConfig:
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.config = configparser.ConfigParser()
        self._migrate_old_config()
        self.load()

    def _migrate_old_config(self):
        if not os.path.exists(self.config_file) and os.path.exists(OLD_CONFIG_FILE):
            try:
                os.makedirs(APP_DATA_DIR, exist_ok=True)
                shutil.move(OLD_CONFIG_FILE, self.config_file)
            except Exception:
                try:
                    shutil.copy2(OLD_CONFIG_FILE, self.config_file)
                except Exception:
                    pass

    def load(self):
        if os.path.exists(self.config_file):
            try:
                self.config.read(self.config_file, encoding='utf-8')
            except Exception:
                pass
        if 'Settings' not in self.config:
            self.config['Settings'] = {}

        defaults = {
            'Theme': 'True',
            'Web_Port': '5000',
            'Web_Host': '127.0.0.1',
            'Web_Password': '',
            'AutoStartWeb': 'True',
            'AutoOpenBrowser': 'False',
            'WebUI_Address': '',
            'WebUI_Port': '',
            'Weight_W1': '70',
            'Weight_W2': '30',
            'Weight_W3': '0'
        }
        changed = False
        for k, v in defaults.items():
            if k not in self.config['Settings']:
                self.config['Settings'][k] = v
                changed = True
        if changed or not os.path.exists(self.config_file):
            self.save()

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
        except Exception:
            pass

    def get(self, key, fallback=''):
        return self.config.get('Settings', key, fallback=fallback)

    def getint(self, key, fallback=0):
        try:
            val = self.config.get('Settings', key, fallback='').strip()
            return int(val) if val else fallback
        except (ValueError, TypeError):
            return fallback

    def getboolean(self, key, fallback=False):
        try:
            return self.config.getboolean('Settings', key, fallback=fallback)
        except (ValueError, TypeError):
            return fallback

    def set(self, key, value):
        if 'Settings' not in self.config:
            self.config['Settings'] = {}
        self.config['Settings'][key] = str(value)

cfg = AppConfig()
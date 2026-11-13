# utils/config.py
import os
import sys
import configparser

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(get_base_dir(), 'config.ini')

class AppConfig:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppConfig, cls).__new__(cls)
            cls._instance.config = configparser.ConfigParser()
            cls._instance.load()
        return cls._instance

    def load(self):
        defaults = {
            'Theme': 'True',
            'LastDrive': 'C:',
            'LastMode': 'moderate',
            'Web_Port': '5000',
            'Web_Host': '0.0.0.0',
            'AutoStartWeb': 'True',
            'AutoOpenBrowser': 'False',
            'WebUI_Address': '',
            'WebUI_Port': ''
        }
        if os.path.exists(CONFIG_FILE):
            self.config.read(CONFIG_FILE, encoding='utf-8')
            if not self.config.has_section('Settings'):
                self.config['Settings'] = defaults
        else:
            self.config['Settings'] = defaults
            self.save()

    def get(self, key, fallback=None):
        return self.config.get('Settings', key, fallback=fallback)

    def getint(self, key, fallback=0):
        try:
            return self.config.getint('Settings', key, fallback=fallback)
        except (ValueError, TypeError):
            return fallback

    def getboolean(self, key, fallback=False):
        try:
            return self.config.getboolean('Settings', key, fallback=fallback)
        except (ValueError, TypeError):
            return fallback

    def set(self, key, value):
        if not self.config.has_section('Settings'):
            self.config['Settings'] = {}
        self.config['Settings'][key] = str(value)

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                self.config.write(f)
            return True
        except Exception as e:
            print(f"Ошибка сохранения config.ini: {e}")
            return False

cfg = AppConfig()
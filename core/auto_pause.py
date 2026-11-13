# core/auto_pause.py
import threading
import datetime
from core.qb_api import send_qb_command
from utils.helpers import write_log, write_error_log

class AutoPauseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AutoPauseManager, cls).__new__(cls)
                cls._instance.timer = None
                cls._instance.info = {
                    'active': False,
                    'hash': None,
                    'name': None,
                    'target_bytes': 0,
                    'target_display': '',
                    'start_time': None,
                    'target_time': None,
                    'remaining_seconds': 0,
                    'speed': 0
                }
        return cls._instance

    def get_status(self):
        if not self.info['active']:
            return {'active': False}
        now = datetime.datetime.now()
        rem = max(0, int((self.info['target_time'] - now).total_seconds()))
        self.info['remaining_seconds'] = rem
        return {
            'active': True,
            'hash': self.info['hash'],
            'name': self.info['name'],
            'target_display': self.info['target_display'],
            'remaining_seconds': rem,
            'target_time_str': self.info['target_time'].strftime('%d.%m.%Y в %H:%M:%S'),
            'speed_bytes': self.info['speed']
        }

    def start_timer(self, qb_ip, qb_port, t_hash, t_name, seconds, target_bytes, target_display, speed, on_complete_cb=None):
        self.cancel_timer()

        def timer_worker():
            write_log('api', f"Авто-пауза: сработал таймер для {t_name} ({t_hash})")
            send_qb_command(qb_ip, qb_port, "stop", t_hash)
            self.info['active'] = False
            if on_complete_cb:
                on_complete_cb(t_hash, t_name)

        now = datetime.datetime.now()
        target_dt = now + datetime.timedelta(seconds=seconds)
        self.info = {
            'active': True,
            'hash': t_hash,
            'name': t_name,
            'target_bytes': target_bytes,
            'target_display': target_display,
            'start_time': now,
            'target_time': target_dt,
            'remaining_seconds': seconds,
            'speed': speed
        }
        self.timer = threading.Timer(seconds, timer_worker)
        self.timer.daemon = True
        self.timer.start()
        write_log('api', f"Таймер авто-паузы запущен на {seconds} сек. для '{t_name}'")
        return target_dt

    def cancel_timer(self):
        if self.timer and self.timer.is_alive():
            self.timer.cancel()
        self.timer = None
        was_active = self.info['active']
        self.info['active'] = False
        if was_active:
            write_log('api', "Таймер авто-паузы отменен пользователем.")
        return was_active

auto_pause_mgr = AutoPauseManager()
# core/site_monitor.py
import os
import threading
import time
import requests
from bs4 import BeautifulSoup
from plyer import notification
from utils.helpers import write_log, write_error_log

# Глобальные переменные для управления мониторингом
_monitoring = False
_stop_event = threading.Event()
_callbacks = []
_monitor_thread = None

# Настройки (можно изменить)
MONITOR_URL = "https://byxatab.com/games/simulator/cities-skylines-ii-2023/18-1-0-3073"
MONITOR_CSS_SELECTOR = 'meta[property="og:title"]'
STATE_FILE = "last_known_version.txt"
CHECK_INTERVAL = 900  # 15 минут

def start_site_monitoring(callback=None):
    global _monitoring, _stop_event, _monitor_thread
    if _monitoring:
        return
    _monitoring = True
    _stop_event.clear()
    if callback and callable(callback):
        _callbacks.append(callback)
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
    _monitor_thread.start()
    write_log('monitor', "Мониторинг сайта запущен")

def stop_site_monitoring():
    global _monitoring, _stop_event
    _monitoring = False
    _stop_event.set()
    write_log('monitor', "Мониторинг сайта остановлен")

def _monitor_loop():
    global _monitoring
    while not _stop_event.is_set() and _monitoring:
        try:
            check_for_updates()
        except Exception as e:
            write_error_log("Ошибка в цикле мониторинга", e)
        for _ in range(CHECK_INTERVAL):
            if _stop_event.is_set() or not _monitoring:
                break
            time.sleep(1)

def check_for_updates():
    try:
        response = requests.get(MONITOR_URL, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        element = soup.select_one(MONITOR_CSS_SELECTOR)
        if not element:
            write_log('monitor', f"Элемент {MONITOR_CSS_SELECTOR} не найден")
            return
        current_version = element.text.strip()
        write_log('monitor', f"Текущая версия: {current_version}")

        last_version = ""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                last_version = f.read().strip()

        if current_version != last_version:
            write_log('monitor', f"Обновление: {last_version} → {current_version}")
            try:
                notification.notify(
                    title="🚀 Обновление на сайте!",
                    message=f"Версия изменилась с {last_version} на {current_version}",
                    app_name="Site Monitor",
                    timeout=10
                )
            except Exception as e:
                write_error_log("Ошибка уведомления", e)
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                f.write(current_version)
            for cb in _callbacks:
                try:
                    cb(last_version, current_version)
                except Exception as e:
                    write_error_log("Ошибка в колбэке мониторинга", e)
        else:
            write_log('monitor', "Изменений нет")
    except Exception as e:
        write_error_log("Ошибка проверки сайта", e)

def check_otvety_status():
    """Проверяет доступность otvet.mail.ru."""
    url = "https://otvet.mail.ru/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            html = response.text.lower()
            if "otvet" in html or "категории" in html or "вопрос" in html:
                return True
            else:
                write_log('monitor', "Ответы: статус 200, но контент заглушка")
                return False
        else:
            write_log('monitor', f"Ответы: HTTP {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        write_log('monitor', "Ответы: таймаут")
        return False
    except Exception as e:
        write_error_log("Ошибка проверки Ответов", e)
        return False

import sys
import os
import argparse
import webbrowser
import threading
import tkinter as tk
from tkinter import messagebox

from utils.config import cfg
from web.app import web_server

# Импортируем родное окно TorrentApp
try:
    from gui.main_window import TorrentApp
except ImportError:
    try:
        from main_window import TorrentApp
    except ImportError as e:
        print(f"❌ Ошибка: не найден файл main_window.py с классом TorrentApp! {e}")
        TorrentApp = None


def parse_arguments():
    parser = argparse.ArgumentParser(description="tbr v2.0 (Швейцарский нож qBittorrent)")
    parser.add_argument("--port", type=int, default=None, help="Порт веб-сервера")
    parser.add_argument("--host", type=str, default=None, help="Хост веб-сервера")
    parser.add_argument("--web-only", action="store_true", help="Запустить только веб без окна")
    parser.add_argument("--no-web", action="store_true", help="Запустить только окно без веб-сервера")
    return parser.parse_args()


def main():
    args = parse_arguments()

    if args.port:
        cfg.set('Web_Port', args.port)
    if args.host:
        cfg.set('Web_Host', args.host)
    if args.port or args.host:
        cfg.save()

    web_port = cfg.getint('Web_Port', 5000)
    web_host = cfg.get('Web_Host', '127.0.0.1')

    # 1. Запуск встроенного веб-сервера на фоне (для связки и браузера)
    if not args.no_web:
        web_server.start(host=web_host, port=web_port)

    # 2. Если передан флаг --web-only, работаем только как консольный веб-сервер
    if args.web_only:
        webbrowser.open(f"http://{web_host}:{web_port}")
        print(f"✅ Сервер запущен на http://{web_host}:{web_port}. Нажмите Ctrl+C для выхода.")
        try:
            while True:
                threading.Event().wait(1)
        except KeyboardInterrupt:
            sys.exit(0)

    # 3. Запуск классического окна Windows (Tkinter)
    if TorrentApp is None:
        messagebox.showerror(
            "Ошибка запуска",
            "Файл интерфейса main_window.py не найден!\nПоложите его в папку gui/main_window.py."
        )
        return

    # Четкие шрифты на мониторах высокой четкости (HiDPI)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    app = TorrentApp(root)

    # Добавляем в шапку окна кнопку открытия веб-версии
    def open_browser():
        webbrowser.open(f"http://{cfg.get('Web_Host', '127.0.0.1')}:{cfg.getint('Web_Port', 5000)}")

    if hasattr(app, 'tlf'):
        web_btn = tk.Button(
            app.tlf, text="🌐 Веб-интерфейс", font=("Arial", 9, "bold"), bd=0,
            bg="#2ecc71", fg="white", command=open_browser
        )
        web_btn.pack(side="right", padx=5)

    root.mainloop()


if __name__ == "__main__":
    main()
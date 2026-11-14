# gui/main_window.py
import os
import webbrowser
import tkinter as tk
from tkinter import messagebox

from utils.config import cfg
from utils.helpers import LOG_FOLDER
from core.qb_api import detect_qbittorrent_port, is_qb_running, launch_qbittorrent, close_qbittorrent
from core.autostart import set_autostart, is_autostart_enabled
from core.summary_tracker import summary_tracker
from core.torrent_parser import get_global_torrent_summaries


class TorrentApp:
    def __init__(self, root):
        self.root = root
        self.qb_ip, self.qb_port = detect_qbittorrent_port(cfg.config)
        self.port = cfg.getint('Web_Port', 5000)

        self.root.title("tbr PRO — Control Panel")
        self.root.geometry("480x470")
        self.root.minsize(440, 440)
        self.root.configure(bg="#121214")

        summary_tracker.start_auto_export(get_global_torrent_summaries)
        self.build_ui()
        self.update_status()

    def build_ui(self):
        f = tk.Frame(self.root, bg="#1a1a20", bd=1, relief="solid")
        f.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(f, text="⚡ tbr PRO CONTROL PANEL", font=("Segoe UI", 13, "bold"), fg="#2ecc71", bg="#1a1a20").pack(
            pady=(14, 4))
        tk.Label(f, text="Веб-сервер работает в фоне", font=("Segoe UI", 9), fg="#95a5a6", bg="#1a1a20").pack(
            pady=(0, 12))

        tk.Button(f, text="🌐 ОТКРЫТЬ ВЕБ-ИНТЕРФЕЙС", font=("Segoe UI", 11, "bold"), bd=0,
                  bg="#2ecc71", fg="#000000", cursor="hand2", command=self.open_web).pack(fill="x", padx=24, pady=4,
                                                                                          ipady=6)

        net_frame = tk.Frame(f, bg="#262630", bd=0)
        net_frame.pack(fill="x", padx=24, pady=12, ipady=6)

        tk.Label(net_frame, text="Хост и пароль веб-доступа (для 0.0.0.0 пароль обязателен):",
                 font=("Segoe UI", 8, "bold"), fg="#95a5a6", bg="#262630").pack(anchor="w", padx=10, pady=(6, 2))

        row_net = tk.Frame(net_frame, bg="#262630")
        row_net.pack(fill="x", padx=10, pady=2)

        self.e_host = tk.Entry(row_net, width=12, font=("Segoe UI", 9), bg="#1a1a20", fg="#ffffff",
                               insertbackground="#ffffff", bd=0)
        self.e_host.insert(0, cfg.get('Web_Host', '127.0.0.1'))
        self.e_host.pack(side="left", ipady=3, padx=(0, 6))

        self.e_pass = tk.Entry(row_net, show="*", font=("Segoe UI", 9), bg="#1a1a20", fg="#ffffff",
                               insertbackground="#ffffff", bd=0)
        self.e_pass.insert(0, cfg.get('Web_Password', ''))
        self.e_pass.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 6))

        tk.Button(row_net, text="💾", font=("Segoe UI", 9, "bold"), bg="#2ecc71", fg="#000000", bd=0, padx=8,
                  cursor="hand2", command=self.save_net_settings).pack(side="right")

        self.lbl_qb = tk.Label(f, text="qBittorrent: проверка...", font=("Segoe UI", 9, "bold"), fg="#ffffff",
                               bg="#1a1a20")
        self.lbl_qb.pack(pady=(6, 4))

        qb_row = tk.Frame(f, bg="#1a1a20")
        qb_row.pack(fill="x", padx=24, pady=4)
        qb_row.columnconfigure((0, 1), weight=1)

        self.btn_qb_toggle = tk.Button(qb_row, text="Пуск / Стоп qB", font=("Segoe UI", 8, "bold"), bd=0, bg="#262630",
                                       fg="#ffffff", cursor="hand2", command=self.toggle_qb)
        self.btn_qb_toggle.grid(row=0, column=0, padx=3, ipady=4, sticky="ew")

        tk.Button(qb_row, text="🔄 Перезапуск qB", font=("Segoe UI", 8, "bold"), bd=0, bg="#262630", fg="#ffffff",
                  cursor="hand2", command=self.restart_qb).grid(row=0, column=1, padx=3, ipady=4, sticky="ew")

        bot_row = tk.Frame(f, bg="#1a1a20")
        bot_row.pack(fill="x", padx=24, pady=(12, 0))
        bot_row.columnconfigure((0, 1), weight=1)

        self.btn_auto = tk.Button(bot_row, text="Автозагрузка", font=("Segoe UI", 8, "bold"), bd=0, bg="#262630",
                                  fg="#ffffff", cursor="hand2", command=self.toggle_autostart)
        self.btn_auto.grid(row=0, column=0, padx=3, ipady=4, sticky="ew")

        tk.Button(bot_row, text="📁 Папка логов", font=("Segoe UI", 8, "bold"), bd=0, bg="#262630", fg="#ffffff",
                  cursor="hand2", command=lambda: os.startfile(LOG_FOLDER)).grid(row=0, column=1, padx=3, ipady=4,
                                                                                 sticky="ew")

    def save_net_settings(self):
        host = self.e_host.get().strip() or '127.0.0.1'
        pwd = self.e_pass.get().strip()
        if host not in ('127.0.0.1', 'localhost') and not pwd:
            return messagebox.showwarning("Внимание", "Для хоста 0.0.0.0 обязательно впишите пароль!")
        cfg.set('Web_Host', host)
        cfg.set('Web_Password', pwd)
        cfg.save()
        messagebox.showinfo("Сохранено", "Настройки сохранены!\nПерезапустите tbr, чтобы применить новый хост.")

    def open_web(self):
        webbrowser.open(f"http://127.0.0.1:{self.port}/")

    def update_status(self):
        running = is_qb_running()
        if running:
            self.lbl_qb.config(text="qBittorrent: 🟢 Запущен", fg="#2ecc71")
            self.btn_qb_toggle.config(text="⏹ Остановить qB", bg="#e74c3c", fg="#ffffff")
        else:
            self.lbl_qb.config(text="qBittorrent: 🔴 Остановлен", fg="#e74c3c")
            self.btn_qb_toggle.config(text="▶ Запустить qB", bg="#2ecc71", fg="#000000")

        auto_on = is_autostart_enabled()
        self.btn_auto.config(text="Автозагрузка: ВКЛ" if auto_on else "Автозагрузка: ВЫКЛ",
                             fg="#2ecc71" if auto_on else "#95a5a6")
        self.root.after(3000, self.update_status)

    def toggle_qb(self):
        if is_qb_running():
            close_qbittorrent()
        else:
            launch_qbittorrent()
        self.root.after(1000, self.update_status)

    def restart_qb(self):
        close_qbittorrent()
        self.root.after(1500, launch_qbittorrent)
        self.root.after(2500, self.update_status)

    def toggle_autostart(self):
        curr = is_autostart_enabled()
        ok, msg = set_autostart(not curr)
        messagebox.showinfo("Автозагрузка", msg)
        self.update_status()
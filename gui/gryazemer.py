# gui/gryazemer.py
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import subprocess
from core.disk_utils import get_physical_drives, get_logical_drives, run_disk_check, parse_chkdsk_progress, get_chkdsk_message
from utils.helpers import write_log, write_error_log, LOG_FOLDER
from gui.theme import get_theme_config

class GryazemerWindow:
    def __init__(self, root, config, is_dark_theme):
        self.root = root
        self.config = config
        self.is_dark_theme = is_dark_theme
        self.is_repair_running = False
        self.repair_proc = None
        self.stop_repair = False

        self.win = tk.Toplevel(root)
        self.win.title("Гряземер — Лечение дисков")
        self.win.geometry("780x680")
        self.apply_theme_colors(self.win)

        tk.Label(self.win, text="Выберите диск и режим лечения:", font=("Arial", 11, "bold"),
                 bg=self.win.cget("bg"), fg="white").pack(pady=10)

        # Таблица дисков
        self.disk_tree = ttk.Treeview(self.win, columns=("Model", "Size", "Temp", "Status", "Letters"),
                                      show="tree headings")
        self.disk_tree.pack(fill="both", expand=True, padx=10, pady=5)
        self.disk_tree.heading("#0", text="Физический диск")
        self.disk_tree.heading("Model", text="Модель")
        self.disk_tree.heading("Size", text="Размер")
        self.disk_tree.heading("Temp", text="Температура")
        self.disk_tree.heading("Status", text="Статус")
        self.disk_tree.heading("Letters", text="Тома")
        self.disk_tree.column("#0", width=80, anchor="center")
        self.disk_tree.column("Model", width=200, anchor="w")
        self.disk_tree.column("Size", width=110, anchor="w")
        self.disk_tree.column("Temp", width=90, anchor="center")
        self.disk_tree.column("Status", width=110, anchor="center")
        self.disk_tree.column("Letters", width=100, anchor="center")

        self.disk_tree.tag_configure('Healthy', foreground='#2ecc71')
        self.disk_tree.tag_configure('Warning', foreground='#f1c40f')
        self.disk_tree.tag_configure('Unhealthy', foreground='#e74c3c')
        self.disk_tree.tag_configure('hot', foreground='#e67e22')
        self.disk_tree.tag_configure('ok', foreground='white')

        self._populate_disks()

        # Выбор тома
        select_frame = tk.Frame(self.win, bg=self.win.cget("bg"))
        select_frame.pack(pady=10)
        tk.Label(select_frame, text="Выберите том для проверки:", bg=self.win.cget("bg"), fg="white").pack(side="left", padx=5)
        self.drive_combo = ttk.Combobox(select_frame, state="readonly")
        self.drive_combo['values'] = get_logical_drives()
        last_drive = self.config.get('Settings', 'LastDrive', fallback='C:')
        if last_drive in self.drive_combo['values']:
            self.drive_combo.set(last_drive)
        else:
            self.drive_combo.current(0)
        self.drive_combo.pack(side="left", padx=5)

        # Режим
        mode_frame = tk.Frame(self.win, bg=self.win.cget("bg"))
        mode_frame.pack(pady=5)
        tk.Label(mode_frame, text="Режим:", font=("Arial", 10), bg=self.win.cget("bg"), fg="white").pack(side="left", padx=5)
        self.mode_var = tk.StringVar(value="moderate")
        last_mode = self.config.get('Settings', 'LastMode', fallback='moderate')
        self.mode_var.set(last_mode)

        tk.Radiobutton(mode_frame, text="Умеренный (/f)", variable=self.mode_var, value="moderate",
                       indicatoron=0, width=12, bg=self.win.cget("bg"), fg="white", selectcolor="#e67e22",
                       font=("Arial", 9, "bold")).pack(side="left", padx=5)
        tk.Radiobutton(mode_frame, text="Радикальный (/r)", variable=self.mode_var, value="radical",
                       indicatoron=0, width=12, bg=self.win.cget("bg"), fg="white", selectcolor="#e74c3c",
                       font=("Arial", 9, "bold")).pack(side="left", padx=5)

        # Кнопки
        btn_frame = tk.Frame(self.win, bg=self.win.cget("bg"))
        btn_frame.pack(pady=10)
        self.start_btn = tk.Button(btn_frame, text="Начать проверку", bg="#f39c12", fg="white",
                                   font=("Arial", 10, "bold"), cursor="hand2", command=self.start_repair_thread)
        self.start_btn.pack(side="left", padx=5)
        self.cancel_btn = tk.Button(btn_frame, text="Отмена (Ctrl+C)", state=tk.DISABLED, bg="#e74c3c", fg="white",
                                    font=("Arial", 10, "bold"), command=self.cancel_repair)
        self.cancel_btn.pack(side="left", padx=5)
        self.win.bind('<Control-c>', lambda e: self.cancel_repair())

        # Прогресс
        self.style = ttk.Style()
        self.style.configure("Colored.Horizontal.TProgressbar", background="#f39c12", troughcolor=self.win.cget("bg"))
        self.progress = ttk.Progressbar(self.win, orient="horizontal", length=400, mode="determinate",
                                        style="Colored.Horizontal.TProgressbar")
        self.progress.pack(pady=10)
        self.status_lbl = tk.Label(self.win, text="Готов к запуску", bg=self.win.cget("bg"), fg="white")
        self.status_lbl.pack(pady=5)

        # Лог
        log_frame = tk.Frame(self.win, bg=self.win.cget("bg"))
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        tk.Label(log_frame, text="Лог проверки (в реальном времени):", bg=self.win.cget("bg"), fg="white").pack(anchor="w")
        self.log_output = tk.Text(log_frame, height=10, font=("Consolas", 9), bd=0, state=tk.DISABLED)
        self.log_output.configure(bg=self.win.cget("bg"), fg="white")
        self.log_output.pack(fill="both", expand=True)

        # При закрытии окна сбрасываем состояние
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    def apply_theme_colors(self, win):
        c = get_theme_config(self.is_dark_theme)
        win.configure(bg=c["bm"])

    def _populate_disks(self):
        for item in self.disk_tree.get_children():
            self.disk_tree.delete(item)

        drives = get_physical_drives()
        if drives:
            for idx, d in enumerate(drives):
                temp_val = d.get('temperature')
                if temp_val is not None:
                    try:
                        temp_int = int(temp_val)
                        temp_str = f"{temp_int}°C"
                        temp_tag = 'hot' if temp_int > 50 else 'ok'
                    except (ValueError, TypeError):
                        temp_str = "N/A"
                        temp_tag = 'ok'
                else:
                    temp_str = "N/A"
                    temp_tag = 'ok'

                status_tag = 'Healthy' if d.get('status') != 'Warning' and d.get('status') != 'Unhealthy' else d.get('status', 'Healthy')
                tags = (status_tag, temp_tag) if temp_tag != 'ok' else (status_tag,)

                self.disk_tree.insert("", "end", iid=str(idx), text=f"#{idx+1}",
                                      values=(d.get('model', 'Unknown'),
                                              d.get('size_fmt', 'N/A'),
                                              temp_str,
                                              status_tag,
                                              d.get('letters', '')),
                                      tags=tags)
        else:
            self.disk_tree.insert("", "end", text="Не удалось получить данные дисков (запустите от Администратора)",
                                  values=("", "", "", "", ""))

    def cancel_repair(self):
        self.stop_repair = True
        if self.repair_proc and self.repair_proc.poll() is None:
            self.repair_proc.terminate()
            # Даём время на завершение
            try:
                self.repair_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.repair_proc.kill()
        self.is_repair_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.status_lbl.config(text="Проверка отменена")
        self.progress['value'] = 0
        self.log_output.config(state=tk.NORMAL)
        self.log_output.insert(tk.END, "\n⚠️ ПРОВЕРКА ОТМЕНЕНА ПОЛЬЗОВАТЕЛЕМ.\n")
        self.log_output.config(state=tk.DISABLED)
        write_log('disk', "Проверка отменена пользователем")

    def start_repair_thread(self):
        if self.is_repair_running:
            return
        drive = self.drive_combo.get()
        if not drive:
            return
        mode = self.mode_var.get()
        self.is_repair_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.status_lbl.config(text="Запуск chkdsk...")
        self.progress['value'] = 0
        self.stop_repair = False

        if drive.upper() == "C:":
            if messagebox.askyesno("Критическое предупреждение",
                                   f"Вы выбрали системный диск {drive}.\nПроверка будет запланирована при следующей перезагрузке.\n\nПерезагрузить сейчас?"):
                self.status_lbl.config(text="Перезагрузка через 10 секунд...")
                subprocess.run(["shutdown", "/r", "/t", "10", "/c", f"Запланирована проверка диска {drive}"])
                self.is_repair_running = False
                self.start_btn.config(state=tk.NORMAL)
                self.cancel_btn.config(state=tk.DISABLED)
            else:
                self.is_repair_running = False
                self.start_btn.config(state=tk.NORMAL)
                self.cancel_btn.config(state=tk.DISABLED)
            return

        def run_chkdsk_thread():
            self.repair_proc = run_disk_check(drive, mode)
            if not self.repair_proc:
                self.win.after(0, lambda: self._finish_chkdsk(False, "Ошибка запуска chkdsk"))
                return
            while True:
                if self.stop_repair:
                    break
                line = self.repair_proc.stdout.readline()
                if not line:
                    break
                self.win.after(0, lambda l=line: self._append_log(l))
                percent = parse_chkdsk_progress(line)
                if percent is not None:
                    self.win.after(0, lambda p=percent: self._update_progress(p))
            self.repair_proc.wait()
            if not self.stop_repair:
                msg = get_chkdsk_message(self.repair_proc.returncode)
                self.win.after(0, lambda: self._finish_chkdsk(True, msg))
            else:
                self.win.after(0, lambda: self._finish_chkdsk(False, "Отменено пользователем"))

        threading.Thread(target=run_chkdsk_thread, daemon=True).start()

    def _append_log(self, line):
        self.log_output.config(state=tk.NORMAL)
        self.log_output.insert(tk.END, line)
        self.log_output.see(tk.END)
        self.log_output.config(state=tk.DISABLED)

    def _update_progress(self, percent):
        self.progress.config(value=percent)
        self.status_lbl.config(text=f"Выполнено: {percent}%")

    def _finish_chkdsk(self, success, msg):
        self.is_repair_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        if success:
            self.status_lbl.config(text=msg)
            self.progress.config(value=100)
            self.log_output.config(state=tk.NORMAL)
            self.log_output.insert(tk.END, "\n✅ Проверка завершена.\n")
            self.log_output.config(state=tk.DISABLED)
        else:
            self.status_lbl.config(text=f"❌ {msg}")
            self.progress.config(value=0)

    def _on_close(self):
        if self.is_repair_running:
            self.cancel_repair()
        self.win.destroy()
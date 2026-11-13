# gui/merger.py
import os
import time
import shutil
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading

from core.torrent_parser import get_all_torrents
from core.qb_api import is_qb_running, close_qbittorrent, launch_qbittorrent, get_qb_executable_path
from utils.bencode import decode_bencode, encode_bencode
from utils.helpers import write_error_log
from gui.theme import get_theme_config


class MergerWindow:
    def __init__(self, root, config, is_dark_theme):
        self.root = root
        self.config = config
        self.is_dark_theme = is_dark_theme
        self.bt_backup_path = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'qBittorrent', 'BT_backup')
        self.torrents = []
        self.display_mode = tk.StringVar(value="both")

        self.win = tk.Toplevel(root)
        self.win.title("🔀 Подменщик раздач (.fastresume)")
        self.win.geometry("940x700")

        c = get_theme_config(self.is_dark_theme)
        self.win.configure(bg=c["bm"])

        self.style = ttk.Style(self.win)
        self.style.theme_use("clam")
        self.style.configure("Merger.Treeview", background=c["bt"], foreground=c["ft"],
                             fieldbackground=c["bt"], borderwidth=0, font=("Segoe UI", 9))
        self.style.configure("Merger.Treeview.Heading", background=c["tc"], foreground=c["ft"], borderwidth=0,
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Merger.Treeview", background=[('selected', '#2ecc71')])

        top_frame = tk.Frame(self.win, bg=c["bm"])
        top_frame.pack(fill="x", padx=15, pady=(12, 0))

        tk.Label(top_frame, text="Отображение:", font=("Segoe UI", 9, "bold"), bg=c["bm"], fg=c["fl"]).pack(side="left",
                                                                                                            padx=(0,
                                                                                                                  10))
        for text_val, mode_val in [("Имя", "name"), ("Хэш", "hash"), ("Имя + Хэш", "both")]:
            tk.Radiobutton(top_frame, text=text_val, variable=self.display_mode, value=mode_val,
                           bg=c["bm"], fg=c["ft"], selectcolor=c["bp"], activebackground=c["bi"],
                           font=("Segoe UI", 9), command=self.update_display_lists).pack(side="left", padx=4)

        lists_frame = tk.Frame(self.win, bg=c["bm"])
        lists_frame.pack(fill="both", expand=True, padx=15, pady=10)

        # Слева: Источник
        left_f = tk.Frame(lists_frame, bg=c["bm"])
        left_f.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(left_f, text="1. Старая раздача (ИСТОЧНИК статистики):", font=("Segoe UI", 10, "bold"), bg=c["bm"],
                 fg="#e67e22").pack(anchor="w", pady=(0, 4))

        self.old_tree = ttk.Treeview(left_f, columns=("Name",), show="headings", selectmode="browse",
                                     style="Merger.Treeview")
        self.old_tree.heading("Name", text="Название торрента")
        self.old_tree.pack(side="left", fill="both", expand=True)
        sb_old = ttk.Scrollbar(left_f, orient="vertical", command=self.old_tree.yview)
        sb_old.pack(side="right", fill="y")
        self.old_tree.configure(yscrollcommand=sb_old.set)

        # Справа: Приемник
        right_f = tk.Frame(lists_frame, bg=c["bm"])
        right_f.pack(side="right", fill="both", expand=True, padx=(8, 0))
        tk.Label(right_f, text="2. Новая раздача (ПРИЁМНИК):", font=("Segoe UI", 10, "bold"), bg=c["bm"],
                 fg="#2ecc71").pack(anchor="w", pady=(0, 4))

        self.new_tree = ttk.Treeview(right_f, columns=("Name",), show="headings", selectmode="browse",
                                     style="Merger.Treeview")
        self.new_tree.heading("Name", text="Название торрента")
        self.new_tree.pack(side="left", fill="both", expand=True)
        sb_new = ttk.Scrollbar(right_f, orient="vertical", command=self.new_tree.yview)
        sb_new.pack(side="right", fill="y")
        self.new_tree.configure(yscrollcommand=sb_new.set)

        # Терминал лога
        self.log_area = scrolledtext.ScrolledText(self.win, height=8, font=("Consolas", 9), bg=c["bo"], fg=c["fo"],
                                                  bd=0)
        self.log_area.pack(fill="x", padx=15, pady=(0, 10))

        self.run_btn = tk.Button(self.win, text="🚀 БЕЗОПАСНЫЙ ПЕРЕНОС (С АВТО-ПЕРЕЗАПУСКОМ QBIT)", bg="#2ecc71",
                                 fg="#000000",
                                 font=("Segoe UI", 10, "bold"), bd=0, cursor="hand2", command=self.start_merge_thread)
        self.run_btn.pack(fill="x", padx=15, pady=(0, 15), ipady=6)

        self.load_torrents()

    def log(self, msg):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)

    def load_torrents(self):
        self.torrents = []
        try:
            data = get_all_torrents(use_cache=False)
            for t_hash, info in data.items():
                name = str(info.get('name') or t_hash)
                self.torrents.append({'hash': t_hash, 'name': name})
            self.torrents.sort(key=lambda x: x['name'].lower())
            self.update_display_lists()
            self.log(f"✅ Найдено {len(self.torrents)} раздач в папке BT_backup.")
        except Exception as e:
            self.log(f"❌ Ошибка загрузки списка раздач: {e}")
            write_error_log("Merger load_torrents", e)

    def update_display_lists(self):
        self.old_tree.delete(*self.old_tree.get_children())
        self.new_tree.delete(*self.new_tree.get_children())
        mode = self.display_mode.get()
        for t in self.torrents:
            txt = t['name'] if mode == "name" else (t['hash'] if mode == "hash" else f"{t['name']} [{t['hash'][:8]}]")
            self.old_tree.insert("", "end", values=(txt,), iid=t['hash'])
            self.new_tree.insert("", "end", values=(txt,), iid=t['hash'])

    def start_merge_thread(self):
        old_sel = self.old_tree.selection()
        new_sel = self.new_tree.selection()
        if not old_sel or not new_sel:
            return messagebox.showwarning("Внимание", "Выберите раздачу в левом и правом списке!")
        if old_sel[0] == new_sel[0]:
            return messagebox.showwarning("Внимание", "Выберите две разные раздачи!")

        self.run_btn.config(state=tk.DISABLED, text="⏳ Выполняется перенос и перезапуск qBittorrent...")
        threading.Thread(target=self._run_merge_worker, args=(old_sel[0], new_sel[0]), daemon=True).start()

    def _run_merge_worker(self, old_hash, new_hash):
        exe_path = get_qb_executable_path()
        was_running = is_qb_running()
        success = False

        try:
            if was_running:
                self.log("🛑 qBittorrent запущен. Завершаем процесс для предотвращения перезаписи файла...")
                close_qbittorrent()
                time.sleep(1.5)

            # Ищем файлы без учета регистра
            old_file = None
            new_file = None
            for f in os.listdir(self.bt_backup_path):
                f_lower = f.lower()
                if f_lower == (old_hash.lower() + '.fastresume'):
                    old_file = os.path.join(self.bt_backup_path, f)
                if f_lower == (new_hash.lower() + '.fastresume'):
                    new_file = os.path.join(self.bt_backup_path, f)

            if not old_file or not os.path.exists(old_file):
                raise FileNotFoundError(f"Файл {old_hash}.fastresume не найден в BT_backup")
            if not new_file or not os.path.exists(new_file):
                raise FileNotFoundError(f"Файл {new_hash}.fastresume не найден в BT_backup")

            with open(old_file, 'rb') as f:
                old_data = decode_bencode(f.read())
            with open(new_file, 'rb') as f:
                new_data = decode_bencode(f.read())

            fields = ['total_uploaded', 'total_downloaded', 'active_time', 'seeding_time', 'added_time',
                      'completed_time']
            copied_count = 0

            # Безопасный перенос с поддержкой как bytes, так и str ключей
            for fld in fields:
                fld_b = fld.encode('ascii')
                val = None
                if fld in old_data:
                    val = old_data[fld]
                elif fld_b in old_data:
                    val = old_data[fld_b]

                if val is not None:
                    # Записываем в том же формате ключа, который использует целевой файл
                    if fld_b in new_data or any(isinstance(k, bytes) for k in new_data.keys()):
                        new_data[fld_b] = val
                        new_data.pop(fld, None)
                    else:
                        new_data[fld] = val
                        new_data.pop(fld_b, None)

                    self.log(f"   • Перенесено: {fld} = {val}")
                    copied_count += 1

            if copied_count == 0:
                raise ValueError("В исходном файле не найдено полей статистики!")

            # 1. Сначала кодируем данные в памяти
            encoded_bytes = encode_bencode(new_data)

            # 2. Создаем бэкап
            bak_file = new_file + '.bak'
            if not os.path.exists(bak_file):
                shutil.copy2(new_file, bak_file)
                self.log(f"📦 Бэкап сохранен: {os.path.basename(bak_file)}")

            # 3. Записываем только если кодирование прошло на 100% успешно
            with open(new_file, 'wb') as f:
                f.write(encoded_bytes)

            self.log("🎉 Данные успешно записаны в .fastresume!")
            success = True

        except Exception as e:
            self.log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
            write_error_log("Merger Worker Error", e)

        finally:
            # Гарантированный перезапуск qBittorrent в ЛЮБОМ случае (даже при сбое)
            if was_running and not is_qb_running():
                self.log("🚀 Перезапуск qBittorrent...")
                time.sleep(1)
                launch_qbittorrent(exe_path)

            self.win.after(0, lambda: self.run_btn.config(state=tk.NORMAL,
                                                          text="🚀 БЕЗОПАСНЫЙ ПЕРЕНОС (С АВТО-ПЕРЕЗАПУСКОМ QBIT)"))
            if success:
                self.win.after(0, lambda: messagebox.showinfo("Готово",
                                                              "Статистика успешно перенесена!\nqBittorrent перезапущен."))
            else:
                self.win.after(0, lambda: messagebox.showerror("Ошибка переноса",
                                                               "Не удалось завершить операцию. Смотрите лог внизу окна."))
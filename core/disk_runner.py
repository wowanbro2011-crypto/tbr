# core/disk_runner.py
import threading
import subprocess
from core.disk_utils import run_disk_check, parse_chkdsk_progress, get_chkdsk_message
from utils.helpers import write_log


class DiskRunnerManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DiskRunnerManager, cls).__new__(cls)
                cls._instance.proc = None
                cls._instance.is_running = False
                cls._instance.logs = []
                cls._instance.progress = 0
                cls._instance.current_drive = ""
                cls._instance.current_mode = ""
                cls._instance.status_text = "Ожидание"
        return cls._instance

    def get_state(self, last_log_index=0):
        return {
            'is_running': self.is_running,
            'progress': self.progress,
            'drive': self.current_drive,
            'mode': self.current_mode,
            'status_text': self.status_text,
            'logs': self.logs[last_log_index:],
            'total_logs': len(self.logs)
        }

    def start_check(self, drive_letter, mode):
        if self.is_running:
            return False, "Проверка уже запущена!"

        self.is_running = True
        self.progress = 0
        self.logs = []
        self.current_drive = drive_letter
        self.current_mode = mode
        self.status_text = f"Запущен chkdsk {drive_letter} ({mode})..."
        self.logs.append(f"=== Запуск проверки тома {drive_letter} [режим: {mode}] ===")

        def worker():
            self.proc = run_disk_check(drive_letter, mode)
            if not self.proc:
                self.is_running = False
                self.status_text = "Ошибка запуска chkdsk"
                self.logs.append("❌ Не удалось запустить процесс chkdsk.")
                return

            while self.is_running:
                line = self.proc.stdout.readline()
                if not line:
                    break
                clean_line = line.rstrip()
                if clean_line:
                    self.logs.append(clean_line)
                    pct = parse_chkdsk_progress(clean_line)
                    if pct is not None:
                        self.progress = pct
                        self.status_text = f"Выполнено: {pct}%"

            self.proc.wait()
            ret = self.proc.returncode
            self.is_running = False
            msg = get_chkdsk_message(ret)
            self.status_text = msg
            self.logs.append(f"=== Результат: {msg} (код: {ret}) ===")
            write_log('disk', f"chkdsk завершен для {drive_letter} с кодом {ret}")

        threading.Thread(target=worker, daemon=True).start()
        return True, "Проверка успешно запущена"

    def cancel_check(self):
        if not self.is_running:
            return False, "Проверка не выполняется"
        self.is_running = False
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.status_text = "Проверка отменена пользователем"
        self.logs.append("⚠️ ПРОВЕРКА ОТМЕНЕНА ПОЛЬЗОВАТЕЛЕМ.")
        return True, "Проверка отменена"


disk_runner_mgr = DiskRunnerManager()
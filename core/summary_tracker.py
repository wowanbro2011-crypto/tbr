# core/summary_tracker.py
import os
import time
import json
import csv
import datetime
import threading
from utils.helpers import LOG_FOLDER, format_file_size, parse_bytes, parse_speed, write_log, write_error_log

# 1. Папка для автоматических почасовых выгрузок
AUTO_FOLDER = os.path.join(LOG_FOLDER, "auto_hourly")
# 2. Папка для ручных выгрузок и экспортов прогнозов
MANUAL_FOLDER = os.path.join(LOG_FOLDER, "manual_exports")

os.makedirs(AUTO_FOLDER, exist_ok=True)
os.makedirs(MANUAL_FOLDER, exist_ok=True)

def fmt_ratio_h(val):
    if val is None or val <= 0:
        return "0.000 /ч"
    if val < 0.001:
        return f"{val:.4f} /ч"
    if val < 1.0:
        return f"{val:.3f} /ч"
    return f"{val:.2f} /ч"

def fmt_speed(bps):
    if bps is None or bps <= 0:
        return "0 B/s"
    return f"{format_file_size(bps)}/s"

class SummaryTracker:
    def __init__(self, log_folder=LOG_FOLDER):
        self.log_folder = log_folder
        self.auto_folder = AUTO_FOLDER
        self.manual_folder = MANUAL_FOLDER
        self.history_file = os.path.join(self.auto_folder, "summary_history.json")
        self._thread = None
        self._running = False
        self._lock = threading.Lock()

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_history(self, history):
        try:
            cutoff = time.time() - (35 * 86400)
            history = [h for h in history if h.get('timestamp', 0) >= cutoff]
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            write_error_log("Ошибка сохранения summary_history.json", e)

    def record_snapshot(self, summaries):
        """Снимок записывается ТОЛЬКО при плановой автовыгрузке каждый час!"""
        with self._lock:
            history = self._load_history()
            now = time.time()
            t_map = {}
            tot_up = 0
            tot_sz = 0
            for s in summaries:
                h_id = s.get('hash_id') or s.get('hash')
                up = s.get('uploaded', 0)
                tot_up += up
                tot_sz += s.get('size', 0)
                if h_id:
                    t_map[h_id] = up

            history.append({
                'timestamp': now,
                'datetime': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_uploaded': tot_up,
                'total_size': tot_sz,
                'count': len(summaries),
                'torrents': t_map
            })
            self._save_history(history)

    def get_stats(self, summaries):
        """Чистое чтение статистики без добавления ложных промежуточных снимков."""
        with self._lock:
            history = self._load_history()

        now_ts = time.time()
        total_uploaded = sum(s.get('uploaded', 0) for s in summaries)
        total_size = sum(s.get('size', 0) for s in summaries)

        snap_1h = None
        dt_1h = 3600
        snap_24h = None
        dt_24h = 86400

        if history:
            cand_1h = [h for h in history if 1800 <= (now_ts - h['timestamp']) <= 7200]
            if cand_1h:
                snap_1h = min(cand_1h, key=lambda x: abs((now_ts - x['timestamp']) - 3600))
                dt_1h = max(1, now_ts - snap_1h['timestamp'])

            cand_24h = [h for h in history if 72000 <= (now_ts - h['timestamp']) <= 100000]
            if cand_24h:
                snap_24h = min(cand_24h, key=lambda x: abs((now_ts - x['timestamp']) - 86400))
                dt_24h = max(1, now_ts - snap_24h['timestamp'])

        if snap_1h:
            global_hour_volume = max(0, total_uploaded - snap_1h.get('total_uploaded', total_uploaded))
        else:
            global_hour_volume = 0

        if snap_24h:
            global_day_volume = max(0, total_uploaded - snap_24h.get('total_uploaded', total_uploaded))
        else:
            active_times = [s.get('active_seconds', 0) for s in summaries if s.get('active_seconds', 0) > 0]
            max_act = max(active_times) if active_times else 0
            global_day_volume = int((total_uploaded / max_act) * 86400) if max_act > 0 else 0

        if not snap_1h and global_day_volume > 0:
            global_hour_volume = int(global_day_volume / 24)

        global_hour_speed_bps = global_hour_volume / 3600.0 if global_hour_volume > 0 else 0.0
        global_day_speed_bps = global_day_volume / 86400.0 if global_day_volume > 0 else 0.0

        max_act_global = max((s.get('active_seconds', 1) for s in summaries), default=1)
        global_ratio_h_all = (total_uploaded / max(1, max_act_global) * 3600.0 / total_size) if total_size > 0 else 0.0
        global_ratio_h_day = (global_day_volume / 24.0 / total_size) if total_size > 0 else 0.0
        global_ratio_h_hour = (global_hour_volume / total_size) if total_size > 0 else 0.0

        enhanced_items = []
        for s in summaries:
            item = dict(s)
            h_id = s.get('hash_id') or s.get('hash', '')
            up = s.get('uploaded', 0)
            act = s.get('active_seconds', 0)
            sz = s.get('size', 0)

            ratio = round(up / sz, 2) if sz > 0 else 0.0
            item['ratio'] = ratio

            avg_all = (up / act) if act > 0 else 0
            item['speed_all_time'] = avg_all
            item['speed_all_time_fmt'] = fmt_speed(avg_all)

            delta_1h = 0
            if snap_1h and 'torrents' in snap_1h and h_id in snap_1h['torrents']:
                delta_1h = max(0, up - snap_1h['torrents'][h_id])
                sp_1h = delta_1h / dt_1h
            else:
                sp_1h = 0
            item['speed_1h'] = sp_1h
            item['speed_1h_fmt'] = fmt_speed(sp_1h)

            delta_24h = 0
            if snap_24h and 'torrents' in snap_24h and h_id in snap_24h['torrents']:
                delta_24h = max(0, up - snap_24h['torrents'][h_id])
                sp_24h = delta_24h / dt_24h
            else:
                sp_24h = 0
            item['speed_24h'] = sp_24h
            item['speed_24h_fmt'] = fmt_speed(sp_24h)

            vol_1h_bytes = delta_1h if delta_1h > 0 else int(avg_all * 3600)
            vol_24h_bytes = delta_24h if delta_24h > 0 else int(avg_all * 86400)
            item['vol_hour'] = vol_1h_bytes
            item['vol_hour_fmt'] = f"{vol_1h_bytes / (1024 * 1024):.2f} МБ/ч"
            item['vol_day'] = vol_24h_bytes
            item['vol_day_fmt'] = f"{vol_24h_bytes / (1024 * 1024):.2f} МБ/день"

            r_h_all = (avg_all * 3600.0 / sz) if sz > 0 else 0.0
            r_h_hour = (sp_1h * 3600.0 / sz) if sz > 0 else 0.0
            r_h_day = (sp_24h * 3600.0 / sz) if sz > 0 else 0.0

            item['ratio_h_all'] = r_h_all
            item['ratio_h_all_fmt'] = fmt_ratio_h(r_h_all)
            item['ratio_h_hour'] = r_h_hour
            item['ratio_h_hour_fmt'] = fmt_ratio_h(r_h_hour)
            item['ratio_h_day'] = r_h_day
            item['ratio_h_day_fmt'] = fmt_ratio_h(r_h_day)

            enhanced_items.append(item)

        return {
            'total_torrents': len(summaries),
            'total_size': total_size,
            'total_size_fmt': format_file_size(total_size),
            'total_uploaded': total_uploaded,
            'total_uploaded_fmt': format_file_size(total_uploaded),
            'global_hour_volume': global_hour_volume,
            'global_hour_volume_fmt': f"{format_file_size(global_hour_volume)} / час",
            'global_hour_speed_fmt': fmt_speed(global_hour_speed_bps),
            'global_day_volume': global_day_volume,
            'global_day_volume_fmt': f"{format_file_size(global_day_volume)} / день",
            'global_day_speed_fmt': fmt_speed(global_day_speed_bps),
            'global_ratio_h_all_fmt': fmt_ratio_h(global_ratio_h_all),
            'global_ratio_h_day_fmt': fmt_ratio_h(global_ratio_h_day),
            'global_ratio_h_hour_fmt': fmt_ratio_h(global_ratio_h_hour),
            'items': enhanced_items
        }

    def calculate_smart_forecast(self, target_type, target_hash, target_str, speed_str, summaries):
        """Умный калькулятор: 14 дней (70% неделя / 30% 2 недели) или ручной ввод скорости."""
        try:
            is_seedbox = (target_type == 'all' or not target_hash)

            if is_seedbox:
                current_up = sum(s.get('uploaded', 0) for s in summaries)
                total_sz = sum(s.get('size', 0) for s in summaries)
                name = "🌐 Весь сидбокс (суммарно)"
                target_bytes = parse_bytes(target_str, torrent_size=total_sz)
            else:
                t_item = next((s for s in summaries if (s.get('hash_id') == target_hash or s.get('hash') == target_hash)), None)
                if not t_item:
                    return {'success': False, 'error': "Выбранная раздача не найдена!"}
                current_up = t_item.get('uploaded', 0)
                total_sz = t_item.get('size', 0)
                name = t_item.get('name', target_hash)
                target_bytes = parse_bytes(target_str, torrent_size=total_sz)

            remaining_bytes = max(0, target_bytes - current_up)
            if remaining_bytes == 0:
                return {
                    'success': True, 'achieved': True, 'name': name,
                    'current_up_fmt': format_file_size(current_up),
                    'target_fmt': format_file_size(target_bytes),
                    'message': "Цель уже достигнута!"
                }

            is_manual = bool(speed_str and speed_str.strip().lower() not in ('авто', 'auto', ''))
            manual_speed = 0
            if is_manual:
                manual_speed = parse_speed(speed_str)
                if manual_speed <= 0:
                    return {'success': False, 'error': "Скорость должна быть больше 0!"}

            with self._lock:
                history = self._load_history()

            now_ts = time.time()
            days_available = (history[-1]['timestamp'] - history[0]['timestamp']) / 86400.0 if len(history) >= 2 else 0.0

            if not is_manual and (len(history) < 336 or days_available < 14.0):
                return {
                    'success': False, 'need_manual': True,
                    'days_available': round(days_available, 1),
                    'error': f"Недостаточно данных (накоплено {days_available:.1f} из 14 дней). Укажите скорость вручную."
                }

            def get_hist_delta(t_start, t_end):
                c1 = min(history, key=lambda x: abs(x['timestamp'] - t_start))
                c2 = min(history, key=lambda x: abs(x['timestamp'] - t_end))
                u1 = c1.get('total_uploaded', 0) if is_seedbox else c1.get('torrents', {}).get(target_hash, 0)
                u2 = c2.get('total_uploaded', 0) if is_seedbox else c2.get('torrents', {}).get(target_hash, 0)
                return max(0, u2 - u1)

            forecast_24h_rows = []
            projected_24h_volume = 0

            for i in range(24):
                h_start = now_ts + (i * 3600)
                h_end = h_start + 3600
                s_dt = datetime.datetime.fromtimestamp(h_start)
                e_dt = datetime.datetime.fromtimestamp(h_end)

                if is_manual:
                    vol_hour = int(manual_speed * 3600)
                    speed_hour = manual_speed
                    basis_text = "Ручной ввод скорости"
                else:
                    d1 = get_hist_delta(h_start - (168 * 3600), h_end - (168 * 3600))
                    d2 = get_hist_delta(h_start - (336 * 3600), h_end - (336 * 3600))
                    vol_hour = int((0.7 * d1) + (0.3 * d2))
                    speed_hour = vol_hour / 3600.0
                    basis_text = f"Неделя: {d1 / (1024**2):.1f} МБ (70%) + 2 нед.: {d2 / (1024**2):.1f} МБ (30%)"

                projected_24h_volume += vol_hour
                forecast_24h_rows.append({
                    'date': s_dt.strftime('%d.%m'),
                    'hour': f"{s_dt.strftime('%H:00')} – {e_dt.strftime('%H:00')}",
                    'volume_bytes': vol_hour,
                    'volume_mb': f"{vol_hour / (1024 * 1024):.2f} МБ",
                    'speed_fmt': fmt_speed(speed_hour),
                    'basis': basis_text
                })

            max_seconds = 3650 * 86400
            eta_dt = None
            eta_str = ""

            if is_manual:
                seconds_needed = int(remaining_bytes / manual_speed) if manual_speed > 0 else max_seconds + 1
                if seconds_needed <= max_seconds:
                    eta_dt = datetime.datetime.fromtimestamp(now_ts + seconds_needed)
                else:
                    eta_str = f"Более 10 лет (~{seconds_needed // (365*86400)} лет)"
            else:
                simulated_ts = now_ts
                simulated_rem = remaining_bytes
                idx = 0
                while simulated_rem > 0 and (simulated_ts - now_ts) < (365 * 86400):
                    hour_vol = forecast_24h_rows[idx % 24]['volume_bytes']
                    if hour_vol <= 0:
                        hour_vol = max(1, int(projected_24h_volume / 24)) if projected_24h_volume > 0 else 1024
                    if simulated_rem <= hour_vol:
                        simulated_ts += int((simulated_rem / hour_vol) * 3600)
                        simulated_rem = 0
                        break
                    simulated_rem -= hour_vol
                    simulated_ts += 3600
                    idx += 1
                if simulated_rem == 0:
                    eta_dt = datetime.datetime.fromtimestamp(simulated_ts)
                else:
                    eta_str = "Более 1 года при текущем темпе"

            if eta_dt:
                eta_str = eta_dt.strftime('%A, %d.%m.%Y в %H:%M')
                ru_days = {'Monday': 'Понедельник', 'Tuesday': 'Вторник', 'Wednesday': 'Среда',
                           'Thursday': 'Четверг', 'Friday': 'Пятница', 'Saturday': 'Суббота', 'Sunday': 'Воскресенье'}
                for eng, ru in ru_days.items():
                    eta_str = eta_str.replace(eng, ru)

            return {
                'success': True, 'achieved': False, 'name': name,
                'target_type': target_type, 'is_seedbox': is_seedbox, 'is_manual': is_manual,
                'current_up_fmt': format_file_size(current_up),
                'target_fmt': format_file_size(target_bytes),
                'remaining_fmt': format_file_size(remaining_bytes),
                'forecast_24h_vol_fmt': format_file_size(projected_24h_volume),
                'ratio_current': round(current_up / total_sz, 2) if total_sz > 0 else 0.0,
                'ratio_after_24h': round((current_up + projected_24h_volume) / total_sz, 2) if total_sz > 0 else 0.0,
                'eta_str': eta_str,
                'forecast_rows': forecast_24h_rows
            }
        except Exception as e:
            write_error_log("SmartCalc Error", e)
            return {'success': False, 'error': str(e)}

    def export_forecast_csv(self, forecast_data):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        clean_name = "".join(c for c in forecast_data['name'] if c.isalnum() or c in (' ', '_', '-')).strip()[:30]
        filename = f"forecast_24h_{clean_name}_{ts}.csv"
        filepath = os.path.join(self.manual_folder, filename)

        lines = [
            f"# === ПОЧАСОВОЙ ПРОГНОЗ ОТДАЧИ НА 24 ЧАСА ===",
            f"# Объект: {forecast_data['name']}",
            f"# Дата расчета: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Цель: {forecast_data['target_fmt']} | Осталось: {forecast_data['remaining_fmt']}",
            f"# Ожидаемая отдача за следующие 24ч: {forecast_data['forecast_24h_vol_fmt']}",
            f"# Ожидаемое время достижения цели: {forecast_data['eta_str']}",
            f"# Режим: {'Ручной ввод' if forecast_data.get('is_manual') else 'Умная модель (14 дней, 70/30)'}",
            f"# =========================================="
        ]

        try:
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                f.write('\n'.join(lines) + '\n')
                w = csv.writer(f, delimiter=';')
                w.writerow(['Дата', 'Интервал (час)', 'Ожидаемый объём (МБ)', 'Ожидаемая скорость', 'Обоснование расчёта'])
                for r in forecast_data.get('forecast_rows', []):
                    w.writerow([r['date'], r['hour'], r['volume_mb'], r['speed_fmt'], r['basis']])
            return filepath, filename
        except Exception as e:
            write_error_log("Ошибка экспорта прогноза в CSV", e)
            return None, None

    def export_hourly_csv(self, summaries):
        """ПЛАНОВАЯ АВТОВЫГРУЗКА: делает снимок и сохраняет файл в auto_hourly."""
        if not summaries:
            return None
        self.record_snapshot(summaries)
        stats = self.get_stats(summaries)

        ts = datetime.datetime.now().strftime('%Y%m%d_%H00')
        filename = f"summary_hourly_{ts}.csv"
        filepath = os.path.join(self.auto_folder, filename)
        latest_path = os.path.join(self.auto_folder, "summary_auto_latest.csv")

        header_lines = [
            f"# === ПОЧАСОВАЯ ВЫГРУЗКА СВОДКИ РАЗДАЧ (АВТО) ===",
            f"# Дата выгрузки: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Всего раздач: {stats['total_torrents']}",
            f"# Общий объем: {stats['total_size_fmt']}",
            f"# Всего отдано: {stats['total_uploaded_fmt']}",
            f"# Сумма за 1 час: {stats['global_hour_volume_fmt']} ({stats['global_hour_speed_fmt']})",
            f"# Объем в день: {stats['global_day_volume_fmt']} ({stats['global_day_speed_fmt']})",
            f"# Ratio/ч: {stats['global_ratio_h_all_fmt']} (всего) | {stats['global_ratio_h_day_fmt']} (день) | {stats['global_ratio_h_hour_fmt']} (час)",
            f"# Папка: {self.auto_folder}",
            f"# =========================================="
        ]

        for target in [filepath, latest_path]:
            try:
                with open(target, 'w', encoding='utf-8-sig', newline='') as f:
                    f.write('\n'.join(header_lines) + '\n')
                    w = csv.writer(f, delimiter=';')
                    w.writerow([
                        'Имя', 'Хэш', 'Размер (байт)', 'Отдано (байт)', 'Ratio',
                        'Ср. скорость (всё время)', 'Скорость за 1ч', 'Скорость за 24ч',
                        'МБ/ч', 'МБ/день',
                        'Ratio/ч (всего)', 'Ratio/ч (1ч)', 'Ratio/ч (24ч)',
                        'Активно (сек)', 'Дата создания'
                    ])
                    for s in stats['items']:
                        w.writerow([
                            s.get('name', ''),
                            s.get('hash_id', ''),
                            s.get('size', 0),
                            s.get('uploaded', 0),
                            f"{s.get('ratio', 0.0):.2f}",
                            s.get('speed_all_time_fmt', '0 B/s'),
                            s.get('speed_1h_fmt', '0 B/s'),
                            s.get('speed_24h_fmt', '0 B/s'),
                            s.get('vol_hour_fmt', '0.00 МБ/ч'),
                            s.get('vol_day_fmt', '0.00 МБ/день'),
                            s.get('ratio_h_all_fmt', '0.000 /ч'),
                            s.get('ratio_h_hour_fmt', '0.000 /ч'),
                            s.get('ratio_h_day_fmt', '0.000 /ч'),
                            s.get('active_seconds', 0),
                            s.get('created', '')
                        ])
            except Exception as e:
                write_error_log("Ошибка экспорта почасового CSV", e)

        write_log("summary", f"Авто-сводка выгружена в {filename}")
        return filepath

    def save_manual_csv(self, items):
        """РУЧНАЯ ВЫГРУЗКА СВОДКИ: сохраняется в отдельную папку manual_exports без создания снимка."""
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(self.manual_folder, f"summary_manual_{ts}.csv")
        try:
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                f.write(f"# === РУЧНАЯ ВЫГРУЗКА СВОДКИ ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
                f.write(f"# Раздач: {len(items)}\n")
                w = csv.writer(f, delimiter=';')
                w.writerow([
                    'Имя', 'Хэш', 'Размер (байт)', 'Размер (ГБ)', 'Отдано (байт)', 'Отдано (ГБ)',
                    'Ratio', 'Ср. скорость (всё время)', 'Скорость за 1ч', 'Скорость за 24ч',
                    'МБ/ч', 'МБ/день',
                    'Ratio/ч (всего)', 'Ratio/ч (1ч)', 'Ratio/ч (24ч)', 'Дата создания'
                ])
                for s in items:
                    w.writerow([
                        s.get('name', ''), s.get('hash_id', ''),
                        s.get('size', 0), f"{s.get('size', 0) / (1024 ** 3):.2f}",
                        s.get('uploaded', 0), f"{s.get('uploaded', 0) / (1024 ** 3):.2f}",
                        f"{s.get('ratio', 0.0):.2f}",
                        s.get('speed_all_time_fmt', '0 B/s'),
                        s.get('speed_1h_fmt', '0 B/s'),
                        s.get('speed_24h_fmt', '0 B/s'),
                        s.get('vol_hour_fmt', '0.00 МБ/ч'),
                        s.get('vol_day_fmt', '0.00 МБ/день'),
                        s.get('ratio_h_all_fmt', '0.000 /ч'),
                        s.get('ratio_h_hour_fmt', '0.000 /ч'),
                        s.get('ratio_h_day_fmt', '0.000 /ч'),
                        s.get('created', '')
                    ])
        except Exception as e:
            write_error_log("Ошибка ручного сохранения CSV", e)
        return filepath

    def get_torrent_hourly_history(self, t_hash, limit_hours=36):
        with self._lock:
            history = self._load_history()
        recent = history[-limit_hours:] if len(history) > limit_hours else history
        result = []
        prev_up = None
        for snap in recent:
            if t_hash == 'all':
                up = snap.get('total_uploaded', 0)
            else:
                up = snap.get('torrents', {}).get(t_hash)

            if up is not None:
                delta = max(0, up - prev_up) if prev_up is not None else 0
                result.append({
                    'datetime': snap.get('datetime', ''),
                    'timestamp': snap.get('timestamp', 0),
                    'uploaded': up,
                    'uploaded_fmt': format_file_size(up),
                    'delta_bytes': delta,
                    'delta_mb': f"{delta / (1024*1024):.2f} МБ",
                    'speed_fmt': fmt_speed(delta / 3600) if delta > 0 else "0 B/s"
                })
                prev_up = up
        result.reverse()
        return result

    def start_auto_export(self, get_summaries_fn):
        if self._running:
            return
        self._running = True

        def loop():
            try:
                sums = get_summaries_fn()
                if sums:
                    self.export_hourly_csv(sums)
            except Exception as e:
                write_error_log("Ошибка начальной выгрузки сводки", e)

            while self._running:
                now = datetime.datetime.now()
                seconds_until_next_hour = (60 - now.minute - 1) * 60 + (60 - now.second)
                if seconds_until_next_hour <= 0:
                    seconds_until_next_hour = 3600

                for _ in range(seconds_until_next_hour):
                    if not self._running:
                        return
                    time.sleep(1)

                try:
                    sums = get_summaries_fn()
                    if sums:
                        self.export_hourly_csv(sums)
                except Exception as e:
                    write_error_log("Ошибка циклической выгрузки сводки", e)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

summary_tracker = SummaryTracker()
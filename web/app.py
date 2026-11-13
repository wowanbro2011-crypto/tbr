# web/app.py
import os
import sys
import io
import csv
import datetime
import threading
import time
import shutil
import urllib.parse
from flask import Flask, request, jsonify, render_template_string, Response

from utils.config import cfg
from utils.helpers import parse_bytes, parse_speed, format_file_size, LOG_FOLDER, write_log, write_error_log
from utils.bencode import decode_bencode, encode_bencode
from core.torrent_parser import get_all_torrents, force_clear_cache, get_global_torrent_summaries
from core.qb_api import (
    detect_qbittorrent_port, get_live_torrent_info, send_qb_command,
    is_qb_running, close_qbittorrent, launch_qbittorrent, get_qb_executable_path
)
from core.summary_tracker import summary_tracker, AUTO_FOLDER, MANUAL_FOLDER
from core.autostart import set_autostart, is_autostart_enabled

app = Flask(__name__)
BT_BACKUP_PATH = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'qBittorrent', 'BT_backup')

def get_resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)

TEMPLATE_FILE = get_resource_path(os.path.join('web', 'templates', 'index.html'))

def get_html_content():
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    alt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'index.html')
    if os.path.exists(alt_path):
        with open(alt_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "<h1>Шаблон index.html не найден</h1>"


def resolve_log_path(filename):
    """Строго изолирует поиск файлов внутри разрешённых папок логов, защищая от LFI."""
    if not filename:
        return None

    # Очищаем имя от любых попыток выхода за пределы директорий
    clean_name = os.path.basename(filename.replace('\\', '/'))

    # Разрешаем заглядывать только в 3 конкретные папки
    allowed_dirs = [LOG_FOLDER, AUTO_FOLDER, MANUAL_FOLDER]

    # Если это подпапка (например, auto_hourly/файл.csv)
    if '/' in filename or '\\' in filename:
        parts = filename.replace('\\', '/').split('/')
        if len(parts) >= 2:
            subfolder = parts[-2]
            if subfolder == 'auto_hourly':
                allowed_dirs = [AUTO_FOLDER]
            elif subfolder == 'manual_exports':
                allowed_dirs = [MANUAL_FOLDER]
            clean_name = parts[-1]

    for directory in allowed_dirs:
        full_path = os.path.normpath(os.path.join(directory, clean_name))
        # Проверяем, что итоговый путь физически находится внутри разрешенной директории
        if full_path.startswith(os.path.normpath(directory)) and os.path.exists(full_path) and os.path.isfile(
                full_path):
            return full_path

    return None

@app.route('/')
def index():
    return render_template_string(get_html_content())

# === УПРАВЛЕНИЕ QBITTORRENT ===
@app.route('/api/qb/status')
def api_qb_status():
    running = is_qb_running()
    ip, port = detect_qbittorrent_port(cfg.config)
    return jsonify({
        'running': running,
        'ip': ip,
        'port': port,
        'exe_path': get_qb_executable_path()
    })

@app.route('/api/qb/start', methods=['POST'])
def api_qb_start():
    ok = launch_qbittorrent()
    return jsonify({'success': ok, 'message': 'qBittorrent запущен' if ok else 'Не удалось запустить'})

@app.route('/api/qb/stop', methods=['POST'])
def api_qb_stop():
    ok = close_qbittorrent()
    return jsonify({'success': ok, 'message': 'qBittorrent остановлен' if ok else 'Не удалось остановить'})

@app.route('/api/qb/restart', methods=['POST'])
def api_qb_restart():
    close_qbittorrent()
    time.sleep(1.5)
    ok = launch_qbittorrent()
    return jsonify({'success': ok, 'message': 'qBittorrent перезапущен'})

# === АВТОЗАГРУЗКА WINDOWS ===
@app.route('/api/autostart/status')
def api_autostart_status():
    return jsonify({'enabled': is_autostart_enabled()})

@app.route('/api/autostart/toggle', methods=['POST'])
def api_autostart_toggle():
    curr = is_autostart_enabled()
    ok, msg = set_autostart(not curr)
    return jsonify({'success': ok, 'enabled': not curr if ok else curr, 'message': msg})

# === РАЗДАЧИ И УПРАВЛЕНИЕ ===
@app.route('/api/torrents')
def api_torrents():
    ip, port = detect_qbittorrent_port(cfg.config)
    data_dict = get_all_torrents(use_cache=False)
    live_info = get_live_torrent_info(ip, port) if port else {}

    result = []
    for t_id, static in data_dict.items():
        live = live_info.get(t_id, {})
        size = live.get('total_size', static.get('size', 1))
        uploaded = live.get('uploaded', static.get('uploaded', 0))
        ratio = round(uploaded / size, 4) if size > 0 else 0.0
        state = live.get('state', 'seeding' if static.get('active_seconds', 0) > 0 else 'unknown')
        save_path = live.get('save_path', static.get('save_path', ''))

        name = static.get('name', '')
        if not name or name.lower() == t_id.lower() or len(name) == 40:
            if live.get('name'):
                name = live['name']
        if not name:
            name = t_id

        result.append({
            'hash': t_id,
            'name': name,
            'size': size,
            'size_fmt': format_file_size(size),
            'uploaded': uploaded,
            'uploaded_fmt': format_file_size(uploaded),
            'ratio': ratio,
            'state': state,
            'save_path': save_path,
            'active_seconds': static.get('active_seconds', 0)
        })
    result.sort(key=lambda x: str(x['name']).lower())
    return jsonify({'torrents': result, 'qb_connected': bool(port), 'qb_running': is_qb_running()})

@app.route('/api/torrents/refresh', methods=['POST'])
def api_torrents_refresh():
    force_clear_cache()
    return jsonify({'status': 'ok'})

@app.route('/api/torrents/action', methods=['POST'])
def api_torrent_action():
    data = request.get_json() or {}
    action = data.get('action')
    t_hash = data.get('hash')
    if not t_hash:
        return jsonify({'success': False, 'error': 'Не указан хеш'}), 400

    ip, port = detect_qbittorrent_port(cfg.config)
    if not port:
        return jsonify({'success': False, 'error': 'qBittorrent недоступен'}), 400

    ok = send_qb_command(ip, port, action, t_hash)
    return jsonify({'success': ok})

# Глобальная остановка / запуск всех раздач клиента разом
@app.route('/api/torrents/action_all', methods=['POST'])
def api_torrents_action_all():
    data = request.get_json() or {}
    action = data.get('action', 'stop') # 'stop' (pause all) или 'start' (resume all)
    ip, port = detect_qbittorrent_port(cfg.config)
    if not port:
        return jsonify({'success': False, 'error': 'qBittorrent не запущен'}), 400

    ok = send_qb_command(ip, port, action, 'all')
    msg = "Все раздачи поставлены на паузу" if action == 'stop' else "Все раздачи возобновлены"
    return jsonify({'success': ok, 'message': msg})

# === УМНЫЙ КАЛЬКУЛЯТОР & ПРОГНОЗИРОВАНИЕ ===
@app.route('/api/smart_calc', methods=['POST'])
def api_smart_calc():
    data = request.get_json() or {}
    target_type = data.get('target_type', 'torrent') # 'all' или 'torrent'
    target_hash = data.get('hash', '')
    target_str = data.get('target', '')
    speed_str = data.get('speed', '')

    summaries = get_global_torrent_summaries()
    result = summary_tracker.calculate_smart_forecast(target_type, target_hash, target_str, speed_str, summaries)
    return jsonify(result)

@app.route('/api/smart_calc/export', methods=['POST'])
def api_smart_calc_export():
    data = request.get_json() or {}
    forecast_data = data.get('forecast_data')
    if not forecast_data:
        return jsonify({'success': False, 'error': 'Нет данных для экспорта'}), 400

    filepath, filename = summary_tracker.export_forecast_csv(forecast_data)
    if not filepath:
        return jsonify({'success': False, 'error': 'Ошибка создания файла'}), 500

    with open(filepath, 'rb') as f:
        file_bytes = f.read()

    return Response(
        file_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"}
    )

# === ПОДМЕНЩИК .FASTRESUME ===
@app.route('/api/merger/run', methods=['POST'])
def api_merger_run():
    data = request.get_json() or {}
    old_hash = data.get('old_hash')
    new_hash = data.get('new_hash')
    log = []

    if not old_hash or not new_hash or old_hash == new_hash:
        return jsonify({'success': False, 'log': ['❌ Выберите две разные раздачи!']}), 400

    old_file, new_file = None, None
    for f in os.listdir(BT_BACKUP_PATH):
        if f.lower() == (old_hash.lower() + '.fastresume'):
            old_file = os.path.join(BT_BACKUP_PATH, f)
        if f.lower() == (new_hash.lower() + '.fastresume'):
            new_file = os.path.join(BT_BACKUP_PATH, f)

    if not old_file or not os.path.exists(old_file):
        return jsonify({'success': False, 'log': [f'❌ Файл {old_hash}.fastresume не найден!']}), 404
    if not new_file or not os.path.exists(new_file):
        return jsonify({'success': False, 'log': [f'❌ Файл {new_hash}.fastresume не найден!']}), 404

    exe_path = get_qb_executable_path()
    was_running = is_qb_running()

    try:
        if was_running:
            log.append("🛑 Завершаем qBittorrent во избежание порчи данных...")
            close_qbittorrent()
            time.sleep(1.5)

        with open(old_file, 'rb') as f:
            old_data = decode_bencode(f.read())
        with open(new_file, 'rb') as f:
            new_data = decode_bencode(f.read())

        fields = ['total_uploaded', 'total_downloaded', 'active_time', 'seeding_time', 'added_time', 'completed_time']
        copied = 0
        for fld in fields:
            fld_b = fld.encode('ascii')
            val = None
            if fld in old_data:
                val = old_data[fld]
            elif fld_b in old_data:
                val = old_data[fld_b]

            if val is not None:
                if fld_b in new_data or any(isinstance(k, bytes) for k in new_data.keys()):
                    new_data[fld_b] = val
                    new_data.pop(fld, None)
                else:
                    new_data[fld] = val
                    new_data.pop(fld_b, None)

                log.append(f"✅ Скопировано: {fld} = {val}")
                copied += 1

        if copied == 0:
            raise ValueError("Не найдено подходящих полей статистики для копирования!")

        encoded_bytes = encode_bencode(new_data)

        bak = new_file + '.bak'
        if not os.path.exists(bak):
            shutil.copy2(new_file, bak)
            log.append(f"📦 Бэкап создан: {os.path.basename(bak)}")

        with open(new_file, 'wb') as f:
            f.write(encoded_bytes)
        log.append("🎉 Статистика успешно записана в .fastresume!")

        return jsonify({'success': True, 'log': log})

    except Exception as e:
        write_error_log("Ошибка merger API", e)
        log.append(f"❌ Ошибка: {e}")
        return jsonify({'success': False, 'log': log}), 500

    finally:
        if was_running and not is_qb_running():
            log.append("🚀 Перезапуск qBittorrent...")
            launch_qbittorrent(exe_path)

# === СВОДКА И ИСТОРИЯ ===
@app.route('/api/summary')
def api_summary():
    summaries = get_global_torrent_summaries()
    stats = summary_tracker.get_stats(summaries)
    return jsonify(stats)

@app.route('/api/analytics/history')
def api_analytics_history():
    t_hash = request.args.get('hash', 'all')
    limit = request.args.get('limit', 36, type=int)
    hist = summary_tracker.get_torrent_hourly_history(t_hash, limit_hours=limit)
    return jsonify(hist)

# === РУЧНАЯ ВЫГРУЗКА CSV СВОДКИ В manual_exports ===
@app.route('/api/export_csv', methods=['GET', 'POST'])
def api_export_csv():
    if request.method == 'POST':
        req_data = request.get_json() or {}
        items = req_data.get('items', [])
    else:
        summaries = get_global_torrent_summaries()
        stats = summary_tracker.get_stats(summaries)
        items = stats['items']

    summary_tracker.save_manual_csv(items)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'Имя', 'Хэш', 'Размер (байт)', 'Размер (ГБ)', 'Отдано (байт)', 'Отдано (ГБ)',
        'Ratio', 'Ср. скорость (всё время)', 'Скорость за 1ч', 'Скорость за 24ч',
        'МБ/ч', 'МБ/день',
        'Ratio/ч (всего)', 'Ratio/ч (1ч)', 'Ratio/ч (24ч)', 'Дата создания'
    ])
    for s in items:
        writer.writerow([
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
    filename = f"summary_manual_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue().encode('utf-8-sig'), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})

# === СПИСОК ФАЙЛОВ ЛОГОВ ===
@app.route('/api/logs/list')
def api_logs_list():
    files = []
    if os.path.exists(LOG_FOLDER):
        for f in os.listdir(LOG_FOLDER):
            if f.endswith('.log') or f.endswith('.txt'):
                files.append(f)
    if os.path.exists(AUTO_FOLDER):
        for f in os.listdir(AUTO_FOLDER):
            if f.endswith('.csv'):
                files.append(f"auto_hourly/{f}")
    if os.path.exists(MANUAL_FOLDER):
        for f in os.listdir(MANUAL_FOLDER):
            if f.endswith('.csv'):
                files.append(f"manual_exports/{f}")
    return jsonify(sorted(files, reverse=True))

# === ПРОСМОТР СОДЕРЖИМОГО (В ТЕРМИНАЛЕ САЙТА) ===
@app.route('/api/logs/view')
def api_logs_view():
    filename = request.args.get('name', '')
    path = resolve_log_path(filename)
    if not path:
        return jsonify({'error': 'Файл не найден'}), 404
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            return jsonify({'content': "".join(lines[-300:])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === СКАЧИВАНИЕ ФАЙЛА НАПРЯМУЮ В БРАУЗЕР ===
@app.route('/api/logs/download')
def api_logs_download():
    filename = request.args.get('name', '')
    path = resolve_log_path(filename)
    if not path:
        return "Файл не найден на сервере", 404
    try:
        with open(path, 'rb') as f:
            data = f.read()
        base_name = os.path.basename(path)
        mime = "text/csv" if base_name.endswith('.csv') else "text/plain"
        return Response(
            data,
            mimetype=mime,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(base_name)}"}
        )
    except Exception as e:
        return f"Ошибка скачивания: {e}", 500

# === НАСТРОЙКИ ===
@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return jsonify({
            'web_port': cfg.getint('Web_Port', 5000),
            'web_host': cfg.get('Web_Host', '0.0.0.0'),
            'theme': cfg.getboolean('Theme', True),
            'qb_ip': cfg.get('WebUI_Address', ''),
            'qb_port': cfg.get('WebUI_Port', ''),
            'autostart': is_autostart_enabled()
        })
    data = request.get_json() or {}
    old_p = cfg.getint('Web_Port', 5000)
    new_p = int(data.get('web_port', old_p))
    cfg.set('Web_Port', new_p)
    cfg.set('Web_Host', data.get('web_host', cfg.get('Web_Host', '0.0.0.0')))
    if 'theme' in data: cfg.set('Theme', str(data['theme']))
    if 'qb_ip' in data: cfg.set('WebUI_Address', data['qb_ip'])
    if 'qb_port' in data: cfg.set('WebUI_Port', str(data['qb_port']))
    cfg.save()
    return jsonify({'success': True, 'port_changed': old_p != new_p, 'new_port': new_p, 'message': 'Настройки сохранены'})

class WebServerController:
    def __init__(self):
        self.server_instance = None

    def start(self, host=None, port=None):
        from werkzeug.serving import make_server
        h = host or cfg.get('Web_Host', '0.0.0.0')
        if not h or h == '127.0.0.1':
            h = '0.0.0.0'
        p = port or cfg.getint('Web_Port', 5000)

        # Запуск плановой автовыгрузки
        summary_tracker.start_auto_export(get_global_torrent_summaries)

        def serve():
            try:
                self.server_instance = make_server(h, p, app, threaded=True)
                print("\n" + "="*50)
                print(f"🚀 ВЕБ-СЕРВЕР tbr УСПЕШНО ЗАПУЩЕН НА {h}:{p}")
                print(f"👉 Локально на этом ПК: http://127.0.0.1:{p}")
                print(f"👉 Через Localhost:     http://localhost:{p}")
                try:
                    import socket
                    hn = socket.gethostname()
                    for ext_ip in socket.gethostbyname_ex(hn)[2]:
                        if ext_ip != '127.0.0.1':
                            print(f"👉 Сеть / NetBird:       http://{ext_ip}:{p}")
                except Exception:
                    pass
                print("="*50 + "\n")
                self.server_instance.serve_forever()
            except Exception as e:
                print(f"❌ КРИТИЧЕСКАЯ ОШИБКА СЕРВЕРА: {e}")
                write_error_log("WebServerController", e)

        threading.Thread(target=serve, daemon=True).start()

web_server = WebServerController()

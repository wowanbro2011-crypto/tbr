# web/app.py
import os
import sys
import io
import re
import csv
import hmac
import secrets
import ipaddress
import datetime
import threading
import time
import shutil
import urllib.parse
from flask import Flask, request, jsonify, render_template, redirect, session, Response

from utils.config import cfg
from utils.helpers import format_file_size, sanitize_csv_cell, LOG_FOLDER, write_error_log
from utils.bencode import decode_bencode, encode_bencode
from core.torrent_parser import get_all_torrents, force_clear_cache, get_global_torrent_summaries
from core.qb_api import (
    detect_qbittorrent_port, get_live_torrent_info, send_qb_command,
    is_qb_running, close_qbittorrent, launch_qbittorrent, get_qb_executable_path
)
from core.summary_tracker import summary_tracker, AUTO_FOLDER, MANUAL_FOLDER
from core.autostart import set_autostart, is_autostart_enabled

def get_resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)

app = Flask(
    __name__,
    template_folder=get_resource_path(os.path.join('web', 'templates')),
    static_folder=get_resource_path(os.path.join('web', 'static'))
)
app.secret_key = os.urandom(24)

BT_BACKUP_PATH = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'qBittorrent', 'BT_backup')
BUILD_VER = str(int(time.time()))
HASH_RE = re.compile(r'^[0-9a-fA-F]{40}$')

def get_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def is_allowed_qb_ip(ip_str):
    """Разрешает только пустое значение, localhost, закрытые LAN и подсеть NetBird (100.64.0.0/10)."""
    s = (ip_str or '').strip().lower()
    if s in ('', 'localhost'):
        return True
    try:
        ip_obj = ipaddress.ip_address(s)
        cgnat_net = ipaddress.ip_network('100.64.0.0/10')
        return ip_obj.is_loopback or ip_obj.is_private or (ip_obj in cgnat_net)
    except ValueError:
        return False

def resolve_log_path(filename):
    """Безопасный поиск лога в разрешенных папках с обработкой разных дисков через commonpath."""
    if not filename or not isinstance(filename, str):
        return None
    clean = os.path.basename(filename.replace('\\', '/'))
    allowed_dirs = [LOG_FOLDER, AUTO_FOLDER, MANUAL_FOLDER]

    if '/' in filename or '\\' in filename:
        parts = [p for p in filename.replace('\\', '/').split('/') if p]
        if len(parts) >= 2:
            sub = parts[-2]
            if sub == 'auto_hourly':
                allowed_dirs = [AUTO_FOLDER]
            elif sub == 'manual_exports':
                allowed_dirs = [MANUAL_FOLDER]
            clean = parts[-1]

    for directory in allowed_dirs:
        try:
            norm_dir = os.path.abspath(directory)
            full_path = os.path.abspath(os.path.join(norm_dir, clean))
            if os.path.commonpath([norm_dir, full_path]) == norm_dir and os.path.isfile(full_path):
                return full_path
        except ValueError:
            continue
    return None

@app.before_request
def security_middleware():
    if request.path.startswith('/static/'):
        return None

    is_exposed = app.config.get('IS_EXPOSED', False)
    if is_exposed and request.path != '/login':
        if not session.get('authenticated'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Требуется авторизация'}), 401
            return redirect('/login')

    if request.method == 'POST':
        expected_token = session.get('csrf_token')
        sent_token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')

        origin = request.headers.get('Origin') or request.headers.get('Referer')
        allowed_hosts = {request.host}
        for hdr in ('X-Forwarded-Host', 'X-Original-Host'):
            if request.headers.get(hdr):
                allowed_hosts.add(request.headers.get(hdr).split(',')[0].strip())

        origin_ok = True
        if origin:
            parsed = urllib.parse.urlparse(origin)
            if parsed.netloc and parsed.netloc not in allowed_hosts:
                origin_ok = False

        token_ok = bool(expected_token and sent_token and hmac.compare_digest(str(expected_token), str(sent_token)))
        if not token_ok or not origin_ok:
            return jsonify({'error': 'CSRF проверка не пройдена. Обновите страницу.'}), 403

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html', csrf_token=get_csrf_token(), error=None)
    pwd = request.form.get('password', '')
    real_pwd = cfg.get('Web_Password', '')
    if real_pwd and hmac.compare_digest(pwd, real_pwd):
        session['authenticated'] = True
        return redirect('/')
    return render_template('login.html', csrf_token=get_csrf_token(), error='Неверный пароль!'), 401

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.pop('authenticated', None)
    return redirect('/login')

@app.route('/')
def index():
    return render_template(
        'index.html',
        csrf_token=get_csrf_token(),
        auth_enabled=app.config.get('IS_EXPOSED', False),
        v=BUILD_VER
    )

@app.route('/api/qb/status')
def api_qb_status():
    running = is_qb_running()
    ip, port = detect_qbittorrent_port(cfg.config)
    return jsonify({'running': running, 'ip': ip, 'port': port})

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

@app.route('/api/autostart/status')
def api_autostart_status():
    return jsonify({'enabled': is_autostart_enabled()})

@app.route('/api/autostart/toggle', methods=['POST'])
def api_autostart_toggle():
    curr = is_autostart_enabled()
    ok, msg = set_autostart(not curr)
    return jsonify({'success': ok, 'enabled': not curr if ok else curr, 'message': msg})

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
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    t_hash = data.get('hash', '')
    if action not in ('stop', 'start', 'setForceStart') or not HASH_RE.fullmatch(str(t_hash)):
        return jsonify({'success': False, 'error': 'Некорректные параметры команды'}), 400

    ip, port = detect_qbittorrent_port(cfg.config)
    if not port:
        return jsonify({'success': False, 'error': 'qBittorrent недоступен'}), 400
    return jsonify({'success': send_qb_command(ip, port, action, t_hash)})

@app.route('/api/torrents/action_all', methods=['POST'])
def api_torrents_action_all():
    data = request.get_json(silent=True) or {}
    action = data.get('action', 'stop')
    if action not in ('stop', 'start'):
        return jsonify({'success': False, 'error': 'Неизвестная команда'}), 400
    ip, port = detect_qbittorrent_port(cfg.config)
    if not port:
        return jsonify({'success': False, 'error': 'qBittorrent не запущен'}), 400
    ok = send_qb_command(ip, port, action, 'all')
    msg = "Все раздачи поставлены на паузу" if action == 'stop' else "Все раздачи возобновлены"
    return jsonify({'success': ok, 'message': msg})

@app.route('/api/smart_calc', methods=['POST'])
def api_smart_calc():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': 'Неверный формат JSON'}), 400
    target_type = str(data.get('target_type', 'torrent'))
    target_hash = str(data.get('hash', ''))
    target_str = str(data.get('target', ''))[:64]
    speed_str = str(data.get('speed', ''))[:64]

    summaries = get_global_torrent_summaries()
    result = summary_tracker.calculate_smart_forecast(target_type, target_hash, target_str, speed_str, summaries)
    return jsonify(result)

@app.route('/api/smart_calc/export', methods=['POST'])
def api_smart_calc_export():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': 'Ожидался JSON объект'}), 400
    forecast_data = data.get('forecast_data')
    if not isinstance(forecast_data, dict):
        return jsonify({'success': False, 'error': 'Отсутствует forecast_data'}), 400
    rows = forecast_data.get('forecast_rows')
    if not isinstance(rows, list) or len(rows) > 100 or not all(isinstance(r, dict) for r in rows):
        return jsonify({'success': False, 'error': 'Некорректные строки прогноза'}), 400

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

@app.route('/api/merger/run', methods=['POST'])
def api_merger_run():
    data = request.get_json(silent=True) or {}
    old_hash = str(data.get('old_hash', '')).strip()
    new_hash = str(data.get('new_hash', '')).strip()
    log = []

    if not HASH_RE.fullmatch(old_hash) or not HASH_RE.fullmatch(new_hash) or old_hash.lower() == new_hash.lower():
        return jsonify({'success': False, 'log': ['❌ Некорректные или одинаковые 40-значные хэши!']}), 400

    old_file, new_file = None, None
    if os.path.exists(BT_BACKUP_PATH):
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
            val = old_data.get(fld) if fld in old_data else old_data.get(fld_b)
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

@app.route('/api/summary')
def api_summary():
    summaries = get_global_torrent_summaries()
    return jsonify(summary_tracker.get_stats(summaries))

@app.route('/api/analytics/history')
def api_analytics_history():
    t_hash = request.args.get('hash', 'all')
    if t_hash != 'all' and not HASH_RE.fullmatch(t_hash):
        return jsonify([])
    limit = min(100, max(1, request.args.get('limit', 36, type=int)))
    return jsonify(summary_tracker.get_torrent_hourly_history(t_hash, limit_hours=limit))

@app.route('/api/export_csv', methods=['GET', 'POST'])
def api_export_csv():
    if request.method == 'POST':
        req_data = request.get_json(silent=True)
        if not isinstance(req_data, dict):
            return jsonify({'error': 'Некорректный JSON'}), 400
        items = req_data.get('items')
        if not isinstance(items, list) or len(items) > 5000 or not all(isinstance(x, dict) for x in items):
            return jsonify({'error': 'Некорректный список или превышен лимит 5000 строк'}), 400
    else:
        summaries = get_global_torrent_summaries()
        items = summary_tracker.get_stats(summaries)['items']

    summary_tracker.save_manual_csv(items)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'Имя', 'Хэш', 'Размер (байт)', 'Размер (ГБ)', 'Отдано (байт)', 'Отдано (ГБ)',
        'Ratio', 'Ср. скорость (всё время)', 'Скорость за 1ч', 'Скорость за 24ч',
        'МБ/ч', 'МБ/день', 'Ratio/ч (всего)', 'Ratio/ч (1ч)', 'Ratio/ч (24ч)', 'Дата создания'
    ])
    for s in items:
        sz = int(s.get('size', 0)) if isinstance(s.get('size'), (int, float)) else 0
        up = int(s.get('uploaded', 0)) if isinstance(s.get('uploaded'), (int, float)) else 0
        rt = float(s.get('ratio', 0.0)) if isinstance(s.get('ratio'), (int, float)) else 0.0
        writer.writerow([
            sanitize_csv_cell(s.get('name', '')),
            sanitize_csv_cell(s.get('hash_id', '')),
            sz, f"{sz / (1024 ** 3):.2f}",
            up, f"{up / (1024 ** 3):.2f}",
            f"{rt:.2f}",
            sanitize_csv_cell(s.get('speed_all_time_fmt', '0 B/s')),
            sanitize_csv_cell(s.get('speed_1h_fmt', '0 B/s')),
            sanitize_csv_cell(s.get('speed_24h_fmt', '0 B/s')),
            sanitize_csv_cell(s.get('vol_hour_fmt', '0.00 МБ/ч')),
            sanitize_csv_cell(s.get('vol_day_fmt', '0.00 МБ/день')),
            sanitize_csv_cell(s.get('ratio_h_all_fmt', '0.000 /ч')),
            sanitize_csv_cell(s.get('ratio_h_hour_fmt', '0.000 /ч')),
            sanitize_csv_cell(s.get('ratio_h_day_fmt', '0.000 /ч')),
            sanitize_csv_cell(s.get('created', ''))
        ])
    filename = f"summary_manual_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue().encode('utf-8-sig'), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.route('/api/logs/list')
def api_logs_list():
    entries = []
    for folder, prefix, exts in [
        (LOG_FOLDER, '', ('.log', '.txt')),
        (AUTO_FOLDER, 'auto_hourly/', ('.csv',)),
        (MANUAL_FOLDER, 'manual_exports/', ('.csv',))
    ]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.lower().endswith(exts):
                    full = os.path.join(folder, f)
                    try:
                        entries.append((os.path.getmtime(full), f"{prefix}{f}"))
                    except OSError:
                        pass
    entries.sort(key=lambda x: x[0], reverse=True)
    return jsonify([name for _, name in entries[:20]])

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
            data, mimetype=mime,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(base_name)}"}
        )
    except Exception as e:
        return f"Ошибка скачивания: {e}", 500

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return jsonify({
            'web_port': cfg.getint('Web_Port', 5000),
            'web_host': cfg.get('Web_Host', '127.0.0.1'),
            'has_password': bool(cfg.get('Web_Password', '').strip()),
            'qb_ip': cfg.get('WebUI_Address', ''),
            'qb_port': cfg.get('WebUI_Port', ''),
            'w1': cfg.getint('Weight_W1', 70),
            'w2': cfg.getint('Weight_W2', 30),
            'w3': cfg.getint('Weight_W3', 0),
            'autostart': is_autostart_enabled()
        })

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': 'Некорректные данные'}), 400

    old_p = cfg.getint('Web_Port', 5000)
    try:
        new_p = int(data.get('web_port', old_p))
        if not (1 <= new_p <= 65535):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Порт должен быть числом от 1 до 65535'}), 400

    qb_ip = str(data.get('qb_ip', '')).strip()
    if not is_allowed_qb_ip(qb_ip):
        return jsonify({'success': False, 'error': 'Недопустимый IP qBittorrent (разрешены только локальные сети и NetBird)'}), 400

    qb_port_raw = str(data.get('qb_port', '')).strip()
    if qb_port_raw:
        try:
            qbp = int(qb_port_raw)
            if not (1 <= qbp <= 65535):
                raise ValueError
        except ValueError:
            return jsonify({'success': False, 'error': 'Порт qBittorrent должен быть от 1 до 65535'}), 400

    try:
        w1 = int(data.get('w1', cfg.getint('Weight_W1', 70)))
        w2 = int(data.get('w2', cfg.getint('Weight_W2', 30)))
        w3 = int(data.get('w3', cfg.getint('Weight_W3', 0)))
        if w1 < 0 or w2 < 0 or w3 < 0 or (w1 + w2 + w3) <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Веса должны быть >= 0, и хотя бы один вес > 0'}), 400

    new_host = str(data.get('web_host', '127.0.0.1')).strip() or '127.0.0.1'
    new_pass = str(data.get('web_password', '')).strip()
    effective_pass = new_pass if new_pass else cfg.get('Web_Password', '').strip()

    if new_host not in ('127.0.0.1', 'localhost') and not effective_pass:
        return jsonify({'success': False, 'error': 'Для хоста 0.0.0.0 обязательно задайте пароль!'}), 400

    cfg.set('Web_Port', new_p)
    cfg.set('Web_Host', new_host)
    if new_pass:
        cfg.set('Web_Password', new_pass)
    cfg.set('WebUI_Address', qb_ip)
    cfg.set('WebUI_Port', qb_port_raw)
    cfg.set('Weight_W1', w1)
    cfg.set('Weight_W2', w2)
    cfg.set('Weight_W3', w3)
    cfg.save()

    return jsonify({'success': True, 'port_changed': old_p != new_p, 'new_port': new_p, 'message': 'Настройки сохранены!'})

class WebServerController:
    def __init__(self):
        self.server_instance = None

    def start(self, host=None, port=None):
        from werkzeug.serving import make_server
        h = (host or cfg.get('Web_Host', '127.0.0.1')).strip() or '127.0.0.1'
        p = port or cfg.getint('Web_Port', 5000)

        is_exposed = h not in ('127.0.0.1', 'localhost')
        if is_exposed and not cfg.get('Web_Password', '').strip():
            print("⚠️ Внимание: выбран внешний хост, но пароль не задан! Безопасный откат на 127.0.0.1.")
            h = '127.0.0.1'
            is_exposed = False

        app.config['IS_EXPOSED'] = is_exposed
        summary_tracker.start_auto_export(get_global_torrent_summaries)

        def serve():
            try:
                self.server_instance = make_server(h, p, app, threaded=True)
                print(f"🚀 Сервер tbr запущен на http://{h}:{p} (Авторизация: {'ВКЛ' if is_exposed else 'ВЫКЛ'})")
                self.server_instance.serve_forever()
            except Exception as e:
                write_error_log("WebServerController", e)

        threading.Thread(target=serve, daemon=True).start()

web_server = WebServerController()
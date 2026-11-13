# core/torrent_parser.py
import os
import glob
import time
import datetime
from utils.bencode import decode_bencode
from utils.helpers import write_error_log, write_log

BT_BACKUP_PATH = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'qBittorrent', 'BT_backup')

_CACHE = None
_CACHE_TIME = 0
CACHE_TTL = 3


def force_clear_cache():
    global _CACHE, _CACHE_TIME
    _CACHE = None
    _CACHE_TIME = 0


def _extract_str(val):
    if val is None:
        return ""
    if isinstance(val, bytes):
        try:
            return val.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return val.decode('cp1251')
            except Exception:
                return val.decode('latin1', errors='ignore')
    return str(val).strip()


def _get_field(data, *keys):
    if not isinstance(data, dict):
        return None
    for k in keys:
        if k in data and data[k] is not None:
            return data[k]
        if isinstance(k, str):
            kb = k.encode('ascii', errors='ignore')
            if kb in data and data[kb] is not None:
                return data[kb]
    return None


def parse_single_torrent(fastresume_path):
    t_hash = os.path.splitext(os.path.basename(fastresume_path))[0].lower()
    base_dir = os.path.dirname(fastresume_path)

    fr_data = {}
    try:
        with open(fastresume_path, 'rb') as f:
            fr_data = decode_bencode(f.read()) or {}
    except Exception as e:
        write_error_log(f"decode fastresume {t_hash}", e)

    tor_data = {}
    tor_path = os.path.join(base_dir, t_hash + '.torrent')
    if not os.path.exists(tor_path):
        for candidate in os.listdir(base_dir):
            if candidate.lower() == (t_hash + '.torrent'):
                tor_path = os.path.join(base_dir, candidate)
                break

    if os.path.exists(tor_path):
        try:
            with open(tor_path, 'rb') as f:
                tor_data = decode_bencode(f.read()) or {}
        except Exception as e:
            write_error_log(f"decode torrent {t_hash}", e)

    info_dict = _get_field(tor_data, 'info') or {}

    # 1. Извлечение названия
    name = ""
    tor_name = _extract_str(_get_field(info_dict, 'name.utf-8', 'name'))
    if tor_name and tor_name.lower() != t_hash:
        name = tor_name

    if not name:
        qbt_name = _extract_str(_get_field(fr_data, 'qBt-name'))
        if qbt_name and qbt_name.lower() != t_hash:
            name = qbt_name

    if not name:
        fr_name = _extract_str(_get_field(fr_data, 'name'))
        if fr_name and fr_name.lower() != t_hash:
            name = fr_name

    save_path = _extract_str(_get_field(fr_data, 'save_path', 'qBt-savePath'))
    if not name and save_path:
        base_name = os.path.basename(os.path.normpath(save_path))
        if base_name and len(base_name) > 2 and base_name.lower() != t_hash:
            name = base_name

    if not name:
        name = t_hash

    # 2. Извлечение размера
    size = 0
    if 'length' in info_dict or b'length' in info_dict:
        size = int(_get_field(info_dict, 'length') or 0)
    elif 'files' in info_dict or b'files' in info_dict:
        files = _get_field(info_dict, 'files') or []
        size = sum(int(_get_field(f, 'length') or 0) for f in files)

    if size <= 0:
        size = int(_get_field(fr_data, 'total_size', 'total_downloaded') or 1)

    # 3. Статистика
    uploaded = int(_get_field(fr_data, 'total_uploaded') or 0)
    active_seconds = int(_get_field(fr_data, 'active_time', 'seeding_time') or 0)

    # 4. Дата и числовой таймштамп для точной сортировки
    added_time = _get_field(fr_data, 'added_time', 'completed_time', 'creation date')
    if added_time and int(added_time) > 0:
        created_ts = int(added_time)
        created_str = datetime.datetime.fromtimestamp(created_ts).strftime('%d.%m.%Y %H:%M')
    else:
        try:
            mtime = int(os.path.getmtime(fastresume_path))
            created_ts = mtime
            created_str = datetime.datetime.fromtimestamp(mtime).strftime('%d.%m.%Y %H:%M')
        except Exception:
            created_ts = 0
            created_str = "Дата неизвестна"

    # 5. Трекеры
    trackers = []
    raw_trackers = _get_field(fr_data, 'trackers')
    if raw_trackers and isinstance(raw_trackers, list):
        for tr in raw_trackers:
            if isinstance(tr, list) and tr:
                trackers.append(_extract_str(tr[0]))
            elif isinstance(tr, (str, bytes)):
                trackers.append(_extract_str(tr))

    ratio = round(uploaded / size, 2) if size > 0 else 0.0

    return {
        'name': name,
        'hash_id': t_hash,
        'size': size,
        'uploaded': uploaded,
        'ratio': ratio,
        'active_seconds': active_seconds,
        'save_path': save_path,
        'trackers': trackers,
        'created': created_str,
        'created_ts': created_ts,
        'info_hash': t_hash,
        'files': []
    }


def get_all_torrents(use_cache=True):
    global _CACHE, _CACHE_TIME
    now = time.time()
    if use_cache and _CACHE is not None and (now - _CACHE_TIME) < CACHE_TTL:
        return _CACHE

    result = {}
    if not os.path.exists(BT_BACKUP_PATH):
        return result

    for fname in os.listdir(BT_BACKUP_PATH):
        if fname.lower().endswith('.fastresume'):
            full_path = os.path.join(BT_BACKUP_PATH, fname)
            try:
                item = parse_single_torrent(full_path)
                result[item['hash_id']] = item
            except Exception as e:
                write_error_log(f"parse error {fname}", e)

    _CACHE = result
    _CACHE_TIME = now
    return result


def get_global_torrent_summaries():
    data = get_all_torrents(use_cache=False)
    return list(data.values())


def copy_torrent_to_watch(t_hash):
    if not os.path.exists(BT_BACKUP_PATH):
        return False, "Папка BT_backup не найдена"

    tor_path = os.path.join(BT_BACKUP_PATH, t_hash.lower() + '.torrent')
    if not os.path.exists(tor_path):
        for candidate in os.listdir(BT_BACKUP_PATH):
            if candidate.lower() == (t_hash.lower() + '.torrent'):
                tor_path = os.path.join(BT_BACKUP_PATH, candidate)
                break

    if not os.path.exists(tor_path):
        return False, f"Файл {t_hash}.torrent не найден"

    watch_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
    import shutil
    try:
        dest = os.path.join(watch_dir, os.path.basename(tor_path))
        shutil.copy2(tor_path, dest)
        return True, f"Скопировано в {dest}"
    except Exception as e:
        return False, str(e)
# utils/helpers.py
import os
import sys
import datetime
import traceback
import re

# Папка логов перенесена в системную директорию AppData/Local/tbr/logs (вне папки с exe)
LOCAL_APP_DATA = os.environ.get('LOCALAPPDATA', os.path.join(os.path.expanduser('~'), 'AppData', 'Local'))
LOG_FOLDER = os.path.join(LOCAL_APP_DATA, 'tbr', 'logs')
os.makedirs(LOG_FOLDER, exist_ok=True)

def write_log(category, message):
    try:
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_file = os.path.join(LOG_FOLDER, f"{category}.log")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass

def write_error_log(context, error):
    try:
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_file = os.path.join(LOG_FOLDER, "error.log")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] ОШИБКА в {context}: {error}\n")
            f.write(traceback.format_exc() + "\n")
    except Exception:
        pass

def format_file_size(size_bytes):
    if size_bytes is None:
        return "0 B"
    try:
        size = float(size_bytes)
    except (ValueError, TypeError):
        return "0 B"

    if size <= 0:
        return "0 B"

    if size < 1.0:
        return f"{size:.2f} B"

    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
    for unit in units:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

    return f"{size:.2f} EiB"

def parse_bytes(text, torrent_size=0):
    if not text:
        raise ValueError("Цель не может быть пустой!")
    text = text.strip().lower().replace(',', '.')

    m_ratio = re.match(r'^([\d\.]+)\s*(?:x|ratio|р)?$', text)
    if m_ratio:
        ratio = float(m_ratio.group(1))
        if ratio <= 0:
            raise ValueError("Ratio должен быть больше 0!")
        return int(torrent_size * ratio)

    m_size = re.match(r'^([\d\.]+)\s*([a-zа-я]+)?$', text)
    if not m_size:
        raise ValueError("Неверный формат цели!")

    val = float(m_size.group(1))
    unit = (m_size.group(2) or 'b').lower()

    multipliers = {
        'b': 1, 'б': 1, 'байт': 1,
        'k': 1024, 'kb': 1024, 'kib': 1024, 'кб': 1024,
        'm': 1024**2, 'mb': 1024**2, 'mib': 1024**2, 'мб': 1024**2,
        'g': 1024**3, 'gb': 1024**3, 'gib': 1024**3, 'гб': 1024**3,
        't': 1024**4, 'tb': 1024**4, 'tib': 1024**4, 'тб': 1024**4,
        'p': 1024**5, 'pb': 1024**5, 'pib': 1024**5, 'пб': 1024**5
    }

    if unit not in multipliers:
        raise ValueError(f"Неизвестная единица измерения: {unit}")

    return int(val * multipliers[unit])

def parse_speed(text, default_bytes_sec=0):
    if not text or text.strip().lower() in ('авто', 'auto'):
        return default_bytes_sec
    text = text.strip().lower().replace(',', '.')

    m = re.match(r'^([\d\.]+)\s*([a-zа-я/]+)?$', text)
    if not m:
        raise ValueError("Неверный формат скорости!")

    val = float(m.group(1))
    raw_unit = (m.group(2) or 'b').replace('/s', '').replace('/с', '').replace('/сек', '').strip()

    multipliers = {
        'b': 1, 'б': 1,
        'k': 1024, 'kb': 1024, 'kib': 1024, 'кб': 1024,
        'm': 1024**2, 'mb': 1024**2, 'mib': 1024**2, 'мб': 1024**2,
        'g': 1024**3, 'gb': 1024**3, 'gib': 1024**3, 'гб': 1024**3
    }

    unit = raw_unit if raw_unit in multipliers else 'mib'
    return int(val * multipliers[unit])
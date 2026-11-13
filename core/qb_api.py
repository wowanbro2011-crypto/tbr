# core/qb_api.py
import os
import re
import time
import socket
import subprocess
import urllib.request
import urllib.parse
import http.cookiejar
import json
from utils.helpers import write_error_log, write_log

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

def get_local_ips():
    """Возвращает список всех IP адресов (Wi-Fi, Ethernet, NetBird)."""
    ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip != '127.0.0.1' and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])
            for addr in addrs:
                ip = addr.get('addr')
                if ip and ip != '127.0.0.1' and ip not in ips:
                    ips.append(ip)
    except ImportError:
        pass
    return ips

def get_arp_ips():
    ips = []
    try:
        res = subprocess.run(['arp', '-a'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in res.stdout.splitlines():
            m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
            if m and m.group(1) != '127.0.0.1' and m.group(1) not in ips:
                ips.append(m.group(1))
    except Exception:
        pass
    return ips

def get_qb_executable_path():
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "(Get-Process qbittorrent -ErrorAction SilentlyContinue).Path"]
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        path = r.stdout.strip().splitlines()[0] if r.stdout.strip() else None
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\qBittorrent\qbittorrent.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\qBittorrent\qbittorrent.exe"),
        os.path.expandvars(r"%LocalAppData%\Programs\qBittorrent\qbittorrent.exe")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "qbittorrent.exe"

def is_qb_running():
    try:
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq qbittorrent.exe'],
                           capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return 'qbittorrent.exe' in r.stdout.lower()
    except Exception:
        return False

def close_qbittorrent():
    if not is_qb_running():
        return True
    write_log('api', "Завершение процесса qBittorrent...")
    subprocess.run(['taskkill', '/IM', 'qbittorrent.exe'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(15):
        time.sleep(0.5)
        if not is_qb_running():
            return True
    subprocess.run(['taskkill', '/F', '/IM', 'qbittorrent.exe'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(1)
    return not is_qb_running()

def launch_qbittorrent(exe_path=None):
    path = exe_path or get_qb_executable_path()
    try:
        subprocess.Popen([path], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        return True
    except Exception as e:
        write_error_log("Ошибка запуска qBittorrent", e)
        return False

def qb_login(qb_ip, qb_port, username="admin", password=""):
    base_url = f"http://{qb_ip}:{qb_port}"
    login_url = f"{base_url}/api/v2/auth/login"
    data = urllib.parse.urlencode({'username': username, 'password': password}).encode('utf-8')
    req = urllib.request.Request(
        login_url,
        data=data,
        headers={'Referer': base_url, 'Origin': base_url, 'User-Agent': 'Mozilla/5.0'}
    )
    try:
        with opener.open(req, timeout=1.5) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            return "Ok." in body or resp.getcode() == 200
    except Exception:
        return False

def detect_qbittorrent_port(config=None):
    if config:
        try:
            address = config.get('Settings', 'WebUI_Address', fallback='').strip()
            raw_port = config.get('Settings', 'WebUI_Port', fallback='').strip()
            port = int(raw_port) if raw_port.isdigit() else None
            if address and port:
                return address, port
        except Exception:
            pass

    config_path = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'qBittorrent', 'qBittorrent.conf')
    port_from_conf = None
    address_from_conf = '127.0.0.1'

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            m_port = re.search(r'(?:WebUI\\Port|Port)=(\d+)', content, re.IGNORECASE)
            if m_port:
                port_from_conf = int(m_port.group(1))
            m_addr = re.search(r'(?:WebUI\\Address|Address)=([^\s\r\n]+)', content, re.IGNORECASE)
            if m_addr:
                addr = m_addr.group(1).strip()
                if addr not in ('*', '0.0.0.0', ''):
                    address_from_conf = addr
        except Exception:
            pass

        if port_from_conf:
            return address_from_conf, port_from_conf

    ports_to_check = [port_from_conf] if port_from_conf else [8080, 8081, 1488, 8888]
    for port in filter(None, ports_to_check):
        for ip in ['127.0.0.1', 'localhost']:
            try:
                base_url = f"http://{ip}:{port}"
                req = urllib.request.Request(f"{base_url}/api/v2/app/version", headers={'Referer': base_url})
                with opener.open(req, timeout=0.8) as resp:
                    if resp.getcode() == 200:
                        return ip, port
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    qb_login(ip, port)
                    return ip, port
            except Exception:
                continue

    return '127.0.0.1', (port_from_conf or 8080)

def get_live_torrent_info(qb_ip, qb_port):
    if not qb_ip or not qb_port:
        return {}
    if qb_ip in ('*', '0.0.0.0'):
        qb_ip = '127.0.0.1'

    base_url = f"http://{qb_ip}:{qb_port}"
    req = urllib.request.Request(
        f"{base_url}/api/v2/torrents/info",
        headers={'Referer': base_url, 'Origin': base_url, 'User-Agent': 'Mozilla/5.0'}
    )

    try:
        with opener.open(req, timeout=1.2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return {t['hash']: t for t in data}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            if qb_login(qb_ip, qb_port):
                try:
                    with opener.open(req, timeout=1.2) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                        return {t['hash']: t for t in data}
                except Exception:
                    pass
        return {}
    except Exception:
        return {}

def send_qb_command(qb_ip, qb_port, action, hash_val):
    if not qb_ip or not qb_port or not hash_val:
        return False
    if qb_ip in ('*', '0.0.0.0'):
        qb_ip = '127.0.0.1'

    base_url = f"http://{qb_ip}:{qb_port}"
    payload = {'hashes': hash_val}
    if action == 'setForceStart':
        payload['value'] = 'true'

    req = urllib.request.Request(
        f"{base_url}/api/v2/torrents/{action}",
        data=urllib.parse.urlencode(payload).encode('utf-8'),
        method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Referer': base_url, 'Origin': base_url}
    )

    try:
        with opener.open(req, timeout=3) as resp:
            return resp.getcode() == 200
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            if qb_login(qb_ip, qb_port):
                try:
                    with opener.open(req, timeout=3) as resp2:
                        return resp2.getcode() == 200
                except Exception:
                    pass
        return False
    except Exception:
        return False
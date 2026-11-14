// web/static/common.js
const VALID_TABS = ['torrents', 'merger', 'summary', 'analytics'];
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

async function api(url, method = 'GET', body = null) {
    const opts = { method, headers: {} };
    if (method === 'POST') {
        opts.headers['X-CSRF-Token'] = CSRF_TOKEN;
        if (body !== null) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(body);
        }
    }
    const res = await fetch(url, opts);
    if (res.status === 401) {
        window.location.href = '/login';
        throw new Error('Требуется авторизация');
    }
    return res;
}

function formatBytesJS(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
    let val = parseFloat(bytes);
    let u = 0;
    while (val >= 1024 && u < units.length - 1) { val /= 1024; u++; }
    return `${val.toFixed(2)} ${units[u]}`;
}

function parseDateToTs(str) {
    if (!str || typeof str !== 'string' || str.includes('неизвестна')) return 0;
    const parts = str.trim().split(' ');
    if (parts.length < 2) return 0;
    const dmy = parts[0].split('.');
    const hm = parts[1].split(':');
    if (dmy.length !== 3 || hm.length !== 2) return 0;
    return new Date(parseInt(dmy[2]), parseInt(dmy[1]) - 1, parseInt(dmy[0]), parseInt(hm[0]), parseInt(hm[1])).getTime();
}

function switchTab(name, updateHash = true) {
    if (!VALID_TABS.includes(name)) name = 'torrents';
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('active', c.id === 'tab-' + name));
    if (updateHash && window.location.hash !== '#' + name) window.location.hash = name;

    if (name === 'torrents') loadTorrents();
    if (name === 'merger') loadMergerLists();
    if (name === 'summary') loadSummary();
    if (name === 'analytics') loadAnalyticsTab();
}

function syncTabWithHash() {
    const rawHash = (window.location.hash || '').replace('#', '').trim();
    switchTab(VALID_TABS.includes(rawHash) ? rawHash : 'torrents', false);
}
window.addEventListener('hashchange', syncTabWithHash);

async function checkQbStatus() {
    try {
        const res = await api('/api/qb/status');
        const d = await res.json();
        const badge = document.getElementById('qb-status-badge');
        badge.className = d.running ? 'badge badge-up pointer' : 'badge badge-stop pointer';
        badge.textContent = d.running ? '🟢 qB Запущен' : '🔴 qB Остановлен (клик для пуска)';
    } catch (e) {}
}

async function toggleQbPower() {
    const res = await api('/api/qb/status');
    const d = await res.json();
    if (confirm(d.running ? "Закрыть qBittorrent?" : "Запустить qBittorrent?")) {
        await api(`/api/qb/${d.running ? 'stop' : 'start'}`, 'POST');
        setTimeout(checkQbStatus, 1500);
    }
}

async function restartQb() {
    if (confirm("Перезапустить qBittorrent?")) {
        await api('/api/qb/restart', 'POST');
        setTimeout(checkQbStatus, 2000);
    }
}

async function checkAutostart() {
    const res = await api('/api/autostart/status');
    const d = await res.json();
    const btn = document.getElementById('autostart-toggle-btn');
    btn.className = d.enabled ? 'btn btn-danger' : 'btn';
    btn.textContent = d.enabled ? 'Отключить' : 'Включить';
}

async function toggleAutostart() {
    const res = await api('/api/autostart/toggle', 'POST');
    const d = await res.json();
    alert(d.message);
    checkAutostart();
}

async function openSettingsModal() {
    checkAutostart();
    const res = await api('/api/settings');
    const d = await res.json();
    document.getElementById('setting-web-host').value = d.web_host;
    document.getElementById('setting-web-port').value = d.web_port;
    document.getElementById('setting-web-password').value = '';
    document.getElementById('setting-web-password').placeholder = d.has_password ? 'Пароль задан (введите новый для смены)' : 'Задайте пароль (обязательно для 0.0.0.0)';
    document.getElementById('setting-qb-ip').value = d.qb_ip;
    document.getElementById('setting-qb-port').value = d.qb_port;
    document.getElementById('setting-w1').value = d.w1;
    document.getElementById('setting-w2').value = d.w2;
    document.getElementById('setting-w3').value = d.w3;
    document.getElementById('settings-modal').style.display = 'flex';
}

function closeSettingsModal() {
    document.getElementById('settings-modal').style.display = 'none';
}

async function saveSettings() {
    const payload = {
        web_host: document.getElementById('setting-web-host').value.trim(),
        web_port: parseInt(document.getElementById('setting-web-port').value),
        web_password: document.getElementById('setting-web-password').value,
        qb_ip: document.getElementById('setting-qb-ip').value.trim(),
        qb_port: document.getElementById('setting-qb-port').value.trim(),
        w1: parseInt(document.getElementById('setting-w1').value) || 0,
        w2: parseInt(document.getElementById('setting-w2').value) || 0,
        w3: parseInt(document.getElementById('setting-w3').value) || 0
    };
    const res = await api('/api/settings', 'POST', payload);
    const d = await res.json();
    if (!res.ok) return alert(d.error || 'Ошибка сохранения');
    alert(d.message);
    closeSettingsModal();
    if (d.port_changed) setTimeout(() => { window.location.port = payload.web_port; }, 1500);
}

window.onload = () => {
    syncTabWithHash();
    setInterval(checkQbStatus, 5000);
};
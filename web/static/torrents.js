// web/static/torrents.js
let torrentsData = [];
let currentSortCol = 'name';
let currentSortAsc = true;
let selectedHash = null;

const STATUS_MAP = {
    'downloading': { text: 'Скачивается', badge: 'badge-dl' },
    'seeding': { text: 'Раздаётся', badge: 'badge-up' },
    'uploading': { text: 'Раздаётся', badge: 'badge-up' },
    'stalledup': { text: 'Раздача (нет пиров)', badge: 'badge-stall' },
    'stalleddl': { text: 'Ожидание сидов', badge: 'badge-stall' },
    'pausedup': { text: 'На паузе (завершён)', badge: 'badge-pause' },
    'pauseddl': { text: 'На паузе (загрузка)', badge: 'badge-pause' },
    'stoppedup': { text: 'Остановлен', badge: 'badge-stop' },
    'stoppeddl': { text: 'Остановлен', badge: 'badge-stop' },
    'forcedup': { text: 'Форс-раздача', badge: 'badge-force' },
    'forceddl': { text: 'Форс-загрузка', badge: 'badge-force' },
    'checkingup': { text: 'Проверка файлов', badge: 'badge-pause' },
    'checkingdl': { text: 'Проверка файлов', badge: 'badge-pause' },
    'queuedup': { text: 'В очереди', badge: 'badge-pause' },
    'queueddl': { text: 'В очереди', badge: 'badge-pause' },
    'error': { text: 'Ошибка', badge: 'badge-err' },
    'missingfiles': { text: 'Файлы не найдены', badge: 'badge-err' },
    'moving': { text: 'Перемещение', badge: 'badge-dl' },
    'unknown': { text: 'Активен', badge: 'badge-up' }
};

async function loadTorrents(force = false) {
    if (force) await api('/api/torrents/refresh', 'POST');
    const res = await api('/api/torrents');
    const json = await res.json();
    torrentsData = json.torrents || [];
    checkQbStatus();
    applySortAndRender();
    if (document.getElementById('tab-merger').classList.contains('active')) loadMergerLists();
}

function sortTable(col) {
    if (currentSortCol === col) currentSortAsc = !currentSortAsc;
    else { currentSortCol = col; currentSortAsc = (col === 'name' || col === 'save_path'); }
    applySortAndRender();
}

function applySortAndRender() {
    ['name', 'size', 'uploaded', 'ratio', 'state', 'save_path'].forEach(c => {
        const el = document.getElementById('sort-icon-' + c);
        if (el) el.textContent = (c === currentSortCol) ? (currentSortAsc ? ' ▲' : ' ▼') : '';
    });

    torrentsData.sort((a, b) => {
        let vA = a[currentSortCol], vB = b[currentSortCol];
        if (typeof vA === 'string') vA = vA.toLowerCase();
        if (typeof vB === 'string') vB = vB.toLowerCase();
        return vA < vB ? (currentSortAsc ? -1 : 1) : (vA > vB ? (currentSortAsc ? 1 : -1) : 0);
    });
    filterTorrents();
}

function filterTorrents() {
    const q = (document.getElementById('search-box').value || '').toLowerCase();
    renderTorrents(torrentsData.filter(t => (t.name || '').toLowerCase().includes(q) || (t.save_path || '').toLowerCase().includes(q)));
}

function renderTorrents(list) {
    const tbody = document.getElementById('torrents-tbody');
    tbody.innerHTML = '';
    const frag = document.createDocumentFragment();

    list.forEach(t => {
        const tr = document.createElement('tr');
        if (t.hash === selectedHash) tr.classList.add('selected');
        tr.addEventListener('click', () => selectTorrent(t, tr));

        const st = STATUS_MAP[(t.state || '').toLowerCase()] || STATUS_MAP['unknown'];
        tr.innerHTML = `
            <td><strong>${escapeHtml(t.name)}</strong></td>
            <td>${escapeHtml(t.size_fmt)}</td>
            <td>${escapeHtml(t.uploaded_fmt)}</td>
            <td><strong class="accent-txt">${Number(t.ratio).toFixed(2)}x</strong></td>
            <td><span class="badge ${st.badge}">${st.text}</span></td>
            <td class="muted-text" style="font-size:11px;">${escapeHtml(t.save_path)}</td>
        `;
        frag.appendChild(tr);
    });
    tbody.appendChild(frag);
}

function selectTorrent(t, tr) {
    selectedHash = t.hash;
    document.querySelectorAll('#torrents-tbody tr').forEach(r => r.classList.remove('selected'));
    if (tr) tr.classList.add('selected');
    document.getElementById('selected-title').textContent = `${t.name} (${t.size_fmt})`;
}

async function torrentAction(action) {
    if (!selectedHash) return alert("Сначала выберите раздачу!");
    const res = await api('/api/torrents/action', 'POST', { hash: selectedHash, action });
    const d = await res.json();
    if (!d.success && d.error) alert(d.error);
    loadTorrents();
}

async function globalTorrentAction(action) {
    const title = action === 'stop' ? "поставить ВСЕ раздачи на паузу" : "возобновить ВСЕ раздачи";
    if (!confirm(`Вы действительно хотите ${title}?`)) return;
    const res = await api('/api/torrents/action_all', 'POST', { action });
    const d = await res.json();
    alert(d.message || d.error);
    loadTorrents();
}

function goToAnalyticsWithTorrent() {
    if (!selectedHash) return alert("Сначала выберите раздачу в таблице!");
    switchTab('analytics');
    setTimeout(() => {
        const sel = document.getElementById('smart-calc-target-type');
        sel.value = selectedHash;
        onSmartCalcTargetChange();
        document.getElementById('smart-calc-goal').focus();
    }, 150);
}

function loadMergerLists() {
    const o = document.getElementById('merger-old');
    const n = document.getElementById('merger-new');
    if (!torrentsData.length) {
        loadTorrents().then(() => loadMergerLists());
        return;
    }
    o.innerHTML = ''; n.innerHTML = '';
    torrentsData.forEach(t => {
        const txt = `${t.name} [${t.hash.substring(0, 8)}]`;
        const opt1 = document.createElement('option');
        opt1.value = t.hash; opt1.textContent = txt;
        const opt2 = opt1.cloneNode(true);
        o.appendChild(opt1); n.appendChild(opt2);
    });
    if (torrentsData.length > 1) n.selectedIndex = 1;
}

async function runMerger() {
    const logBox = document.getElementById('merger-log');
    const old_hash = document.getElementById('merger-old').value;
    const new_hash = document.getElementById('merger-new').value;
    if (!old_hash || !new_hash) return alert("Выберите обе раздачи!");

    logBox.textContent = '⏳ Безопасная остановка qBittorrent и перенос статистики...';
    const res = await api('/api/merger/run', 'POST', { old_hash, new_hash });
    const d = await res.json();
    logBox.textContent = (d.log || []).join('\n');
}
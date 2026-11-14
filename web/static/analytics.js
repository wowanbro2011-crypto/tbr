// web/static/analytics.js
let lastForecastData = null;

async function loadAnalyticsTab() {
    loadLogsList();
    if (!rawSummaryItems.length) await loadSummary();
    else populateAnalyticsSelectors();
}

function populateAnalyticsSelectors() {
    const fill = (selId) => {
        const sel = document.getElementById(selId);
        if (!sel) return;
        const cur = sel.value;
        sel.innerHTML = '';
        const frag = document.createDocumentFragment();
        const def = document.createElement('option');
        def.value = 'all'; def.textContent = '🌐 Весь сидбокс (суммарно)';
        frag.appendChild(def);
        rawSummaryItems.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.hash_id;
            opt.textContent = `📦 ${t.name}`;
            frag.appendChild(opt);
        });
        sel.appendChild(frag);
        if (cur) sel.value = cur;
    };
    fill('smart-calc-target-type');
    fill('history-torrent-select');
}

function onSmartCalcTargetChange() {
    const val = document.getElementById('smart-calc-target-type').value;
    const lbl = document.getElementById('smart-calc-goal-label');
    const inp = document.getElementById('smart-calc-goal');
    if (val === 'all') {
        lbl.textContent = 'Цель сидбокса (напр: 50 тиб или 100 гиб):';
        inp.placeholder = '50 тиб или 100 GiB';
    } else {
        lbl.textContent = 'Цель раздачи (напр: 2.0x или 80 гиб):';
        inp.placeholder = '2.0x или 80 гиб';
    }
}

async function runSmartCalc() {
    const term = document.getElementById('smart-calc-terminal');
    const targetVal = document.getElementById('smart-calc-target-type').value;
    const isAll = (targetVal === 'all');
    const goal = document.getElementById('smart-calc-goal').value.trim();
    const speed = document.getElementById('smart-calc-speed').value.trim();

    if (!goal) {
        term.textContent = '[ОШИБКА]\nУкажите цель (например: 50 тиб или 2.0x)!';
        return;
    }

    term.textContent = '⏳ Выполняется расчёт прогноза...';
    let d;
    try {
        const res = await api('/api/smart_calc', 'POST', {
            target_type: isAll ? 'all' : 'torrent',
            hash: isAll ? '' : targetVal,
            target: goal,
            speed: speed
        });
        if (!res.ok) {
            term.textContent = `[ОШИБКА СЕРВЕРА HTTP ${res.status}]`;
            return;
        }
        d = await res.json();
    } catch (err) {
        term.textContent = `[ОШИБКА СЕТИ]\n${err.message}`;
        return;
    }

    const btnTable = document.getElementById('btn-toggle-forecast-table');
    const btnCsv = document.getElementById('btn-export-forecast-csv');
    const wrapTable = document.getElementById('smart-res-table-wrap');

    if (!d.success) {
        btnTable.classList.add('hidden');
        btnCsv.classList.add('hidden');
        wrapTable.classList.add('hidden');
        if (d.need_manual) {
            term.textContent =
                `=================================================================\n` +
                `[МАЛО ДАННЫХ ДЛЯ УМНОЙ МОДЕЛИ]\n` +
                `Накоплено: ${d.days_available} из ${d.req_days} требуемых дней истории.\n\n` +
                `👉 Укажите скорость вручную (напр: 25 мб/с), либо уберите 2/3-ю неделю\n` +
                `   в ⚙️ Настройки (оставив вес только у 1-й недели — тогда хватит 7 дн.).\n` +
                `=================================================================`;
        } else {
            term.textContent = `[ОШИБКА]\n${d.error}`;
        }
        return;
    }

    lastForecastData = d;
    btnCsv.classList.remove('hidden');

    if (d.achieved) {
        btnTable.classList.add('hidden');
        term.textContent = `[ЦЕЛЬ ДОСТИГНУТА!]\nОбъект: ${d.name}\nОтдано: ${d.current_up_fmt} | Цель: ${d.target_fmt}`;
        return;
    }

    btnTable.classList.remove('hidden');
    const modeTxt = d.is_manual ? 'Ручной ввод скорости' : `Умная модель (веса ${d.weights_desc})`;
    let out =
        `=================================================================\n` +
        `[РЕЗУЛЬТАТ ПРОГНОЗА]\n` +
        `Объект:        ${d.name}\n` +
        `Отдано сейчас: ${d.current_up_fmt}  -->  Цель: ${d.target_fmt}\n` +
        `Осталось:      ${d.remaining_fmt}\n`;
    if (!d.is_seedbox) out += `Ratio сейчас:  ${d.ratio_current}x  -->  к завтра: ~${d.ratio_after_24h}x\n`;
    out +=
        `-----------------------------------------------------------------\n` +
        `Режим: ${modeTxt}\n` +
        `Прогноз за 24ч: +${d.forecast_24h_vol_fmt}\n` +
        `ТОЧНЫЙ ФИНИШ:   ${d.eta_str}\n` +
        `=================================================================`;
    term.textContent = out;

    const tbody = document.getElementById('smart-res-tbody');
    tbody.innerHTML = '';
    const frag = document.createDocumentFragment();
    (d.forecast_rows || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(r.date)}</td>
            <td><strong>${escapeHtml(r.hour)}</strong></td>
            <td class="purple-txt" style="font-weight:700;">+${escapeHtml(r.volume_mb)}</td>
            <td class="blue-txt" style="font-weight:600;">${escapeHtml(r.speed_fmt)}</td>
            <td class="muted-text" style="font-size:11px;">${escapeHtml(r.basis)}</td>
        `;
        frag.appendChild(tr);
    });
    tbody.appendChild(frag);
}

function toggleForecastTable() {
    const wrap = document.getElementById('smart-res-table-wrap');
    const btn = document.getElementById('btn-toggle-forecast-table');
    const isHidden = wrap.classList.toggle('hidden');
    btn.textContent = isHidden ? '📅 Почасовой прогноз' : '🔼 Скрыть прогноз';
}

async function exportForecastCSV() {
    if (!lastForecastData) return;
    const res = await api('/api/smart_calc/export', 'POST', { forecast_data: lastForecastData });
    if (!res.ok) return alert('Ошибка экспорта');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = window.URL.createObjectURL(blob);
    const ts = new Date().toLocaleString('sv-SE').replace(/[- :]/g, '_');
    a.download = `forecast_24h_${ts}.csv`;
    a.click();
}

async function loadTorrentHourlyHistory() {
    const hash = document.getElementById('history-torrent-select').value || 'all';
    const res = await api(`/api/analytics/history?hash=${encodeURIComponent(hash)}&limit=36`);
    const list = await res.json();
    const tbody = document.getElementById('torrent-history-tbody');
    tbody.innerHTML = '';
    if (!list.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="center-msg">Нет накопленных почасовых снимков</td></tr>';
        return;
    }
    const frag = document.createDocumentFragment();
    list.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(r.datetime)}</td>
            <td>${escapeHtml(r.uploaded_fmt)}</td>
            <td class="purple-txt" style="font-weight:700;">+${escapeHtml(r.delta_mb)}</td>
            <td class="blue-txt" style="font-weight:600;">${escapeHtml(r.speed_fmt)}</td>
        `;
        frag.appendChild(tr);
    });
    tbody.appendChild(frag);
}

async function loadLogsList() {
    const res = await api('/api/logs/list');
    const files = await res.json();
    const sel = document.getElementById('log-file-select');
    sel.innerHTML = '';

    const frag = document.createDocumentFragment();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = '-- Выберите файл (показаны 20 свежих) --';
    frag.appendChild(placeholder);

    files.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f;
        opt.textContent = f;
        frag.appendChild(opt);
    });
    sel.appendChild(frag);

    document.getElementById('download-log-btn').classList.add('hidden');
    document.getElementById('log-view-terminal').textContent = 'Выберите файл из списка выше и нажмите «Просмотр»...';
}

function onLogSelectChange() {
    const name = document.getElementById('log-file-select').value;
    const dlBtn = document.getElementById('download-log-btn');
    if (!name) {
        dlBtn.classList.add('hidden');
        document.getElementById('log-view-terminal').textContent = 'Выберите файл из списка выше и нажмите «Просмотр»...';
        return;
    }
    dlBtn.href = `/api/logs/download?name=${encodeURIComponent(name)}`;
    dlBtn.classList.remove('hidden');
}

async function loadLogContent() {
    const name = document.getElementById('log-file-select').value;
    if (!name) return alert('Сначала выберите файл из списка!');
    onLogSelectChange();
    const res = await api(`/api/logs/view?name=${encodeURIComponent(name)}`);
    const d = await res.json();
    document.getElementById('log-view-terminal').textContent = d.content || d.error || 'Файл пуст';
}
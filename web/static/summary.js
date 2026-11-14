// web/static/summary.js
let rawSummaryItems = [];
let filteredSummaryItems = [];
let summarySortCol = 'uploaded';
let summarySortAsc = false;

async function loadSummary() {
    const res = await api('/api/summary');
    const d = await res.json();
    document.getElementById('sum-count').textContent = d.total_torrents;
    document.getElementById('sum-size').textContent = d.total_size_fmt;
    document.getElementById('sum-uploaded').textContent = d.total_uploaded_fmt;

    document.getElementById('sum-global-hour').textContent = d.global_hour_volume_fmt || '-';
    document.getElementById('sum-global-hour-speed').textContent = d.global_hour_speed_fmt || '-';
    document.getElementById('sum-global-hour-note').textContent = d.global_hour_note || '';
    document.getElementById('sum-global-day').textContent = d.global_day_volume_fmt || '-';
    document.getElementById('sum-global-day-speed').textContent = d.global_day_speed_fmt || '-';
    document.getElementById('sum-ratio-h').textContent = `${d.global_ratio_h_all_fmt} / ${d.global_ratio_h_day_fmt}`;

    rawSummaryItems = d.items || [];
    if (typeof populateAnalyticsSelectors === 'function') populateAnalyticsSelectors();
    applySummaryFilters();
}

function applySummaryFilters() {
    const q = (document.getElementById('sum-filter-search').value || '').toLowerCase();
    const minRatio = parseFloat(document.getElementById('sum-filter-ratio').value) || 0;
    const minUpGb = (parseFloat(document.getElementById('sum-filter-uploaded').value) || 0) * (1024 ** 3);

    filteredSummaryItems = rawSummaryItems.filter(i => {
        if (q && !(i.name || '').toLowerCase().includes(q)) return false;
        if (minRatio > 0 && (i.ratio || 0) < minRatio) return false;
        if (minUpGb > 0 && (i.uploaded || 0) < minUpGb) return false;
        return true;
    });
    applySummarySortAndRender();
}

function resetSummaryFilters() {
    document.getElementById('sum-filter-search').value = '';
    document.getElementById('sum-filter-ratio').value = '';
    document.getElementById('sum-filter-uploaded').value = '';
    applySummaryFilters();
}

function sortSummary(col) {
    if (summarySortCol === col) summarySortAsc = !summarySortAsc;
    else { summarySortCol = col; summarySortAsc = (col === 'name'); }
    applySummarySortAndRender();
}

function applySummarySortAndRender() {
    ['name', 'size', 'uploaded', 'ratio', 'speed_all_time', 'speed_1h', 'speed_24h', 'vol_hour', 'vol_day', 'ratio_h_all', 'created'].forEach(c => {
        const el = document.getElementById('sum-sort-' + c);
        if (el) el.textContent = (c === summarySortCol) ? (summarySortAsc ? ' ▲' : ' ▼') : '';
    });

    filteredSummaryItems.sort((a, b) => {
        let vA = a[summarySortCol], vB = b[summarySortCol];
        if (summarySortCol === 'created') {
            vA = a.created_ts || parseDateToTs(a.created);
            vB = b.created_ts || parseDateToTs(b.created);
        } else {
            if (typeof vA === 'string') vA = vA.toLowerCase();
            if (typeof vB === 'string') vB = vB.toLowerCase();
        }
        return vA < vB ? (summarySortAsc ? -1 : 1) : (vA > vB ? (summarySortAsc ? 1 : -1) : 0);
    });

    const tbody = document.getElementById('summary-tbody');
    tbody.innerHTML = '';
    const frag = document.createDocumentFragment();
    filteredSummaryItems.forEach(i => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${escapeHtml(i.name)}</strong></td>
            <td>${escapeHtml(formatBytesJS(i.size))}</td>
            <td>${escapeHtml(formatBytesJS(i.uploaded))}</td>
            <td><strong class="accent-txt">${parseFloat(i.ratio || 0).toFixed(2)}x</strong></td>
            <td class="blue-txt" style="font-weight:600;">${escapeHtml(i.speed_all_time_fmt)}</td>
            <td class="purple-txt" style="font-weight:600;">${escapeHtml(i.speed_1h_fmt)}</td>
            <td class="orange-txt" style="font-weight:600;">${escapeHtml(i.speed_24h_fmt)}</td>
            <td class="purple-txt" style="font-weight:700;">${escapeHtml(i.vol_hour_fmt)}</td>
            <td class="orange-txt" style="font-weight:700;">${escapeHtml(i.vol_day_fmt)}</td>
            <td class="muted-text" style="font-size:11px;">${escapeHtml(i.ratio_h_all_fmt)}</td>
            <td class="muted-text" style="font-size:11px;">${escapeHtml(i.created)}</td>
        `;
        frag.appendChild(tr);
    });
    tbody.appendChild(frag);
}

async function exportFilteredSummaryCSV() {
    const res = await api('/api/export_csv', 'POST', { items: filteredSummaryItems });
    if (!res.ok) return alert('Ошибка экспорта');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = window.URL.createObjectURL(blob);
    const ts = new Date().toLocaleString('sv-SE').replace(/[- :]/g, '_');
    a.download = `summary_manual_${ts}.csv`;
    a.click();
}
const API_URL = ""; // Relative path

// Status Indicator
function setOnline(online) {
    const el = document.getElementById('status-indicator');
    if (online) {
        el.textContent = 'Online';
        el.style.color = 'var(--success)';
        el.style.borderColor = 'var(--success)';
    } else {
        el.textContent = 'Offline';
        el.style.color = 'var(--error)';
        el.style.borderColor = 'var(--error)';
    }
}

// Config
async function loadConfig() {
    try {
        const res = await fetch(`${API_URL}/config`);
        if (!res.ok) throw new Error();
        const data = await res.json();

        const outInput = document.getElementById('conf-output');
        outInput.value = data.output_dir || "";

        if (data.is_docker) {
            // User requested to hide it completely
            outInput.disabled = true;
            outInput.title = "Gestionado por Docker (Volumen)";
            outInput.parentElement.style.display = 'none';
        }
        document.getElementById('conf-concurrency').value = data.concurrency || 2;
        document.getElementById('conf-format').value = data.format || "opus";

        setOnline(true);
    } catch (e) {
        setOnline(false);
        console.error("Config load failed", e);
    }
}

async function saveConfig() {
    const btn = document.getElementById('btn-save-config');
    const status = document.getElementById('config-status');
    const payload = {
        output_dir: document.getElementById('conf-output').value,
        concurrency: parseInt(document.getElementById('conf-concurrency').value),
        format: document.getElementById('conf-format').value,
    };

    try {
        btn.disabled = true;
        const res = await fetch(`${API_URL}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            status.textContent = "Guardado correctamente";
            status.style.color = "var(--success)";
        } else throw new Error();
    } catch (e) {
        status.textContent = "Error al guardar";
        status.style.color = "var(--error)";
    } finally {
        btn.disabled = false;
        setTimeout(() => status.textContent = "", 3000);
    }
}

// Playlists
async function loadPlaylists() {
    const list = document.getElementById('playlist-list');
    try {
        const res = await fetch(`${API_URL}/playlists`);
        const data = await res.json();

        list.innerHTML = '';
        data.forEach(pl => {
            const item = document.createElement('div');
            item.className = 'list-item';
            item.innerHTML = `
                <div>
                    <strong>${pl.name}</strong>
                    <div style="font-size:0.8rem; color:var(--text-muted)">${pl.urls.length} URL(s)</div>
                </div>
                <div class="actions">
                     <button class="btn btn-secondary" onclick="viewTracks('${pl.id}', '${pl.name.replace(/'/g, "\\'")}')">Ver Tracks</button>
                     <button class="btn btn-danger" onclick="deletePlaylist('${pl.id}')">Eliminar</button>
                </div>
            `;
            list.appendChild(item);
        });
    } catch (e) {
        console.error(e);
    }
}

async function viewTracks(id, name) {
    const modal = document.getElementById('tracks-modal');
    const title = document.getElementById('modal-title');
    const list = document.getElementById('tracks-list');

    title.textContent = `Tracks: ${name}`;
    list.innerHTML = '<li>Cargando...</li>';
    modal.style.display = 'block';

    try {
        const res = await fetch(`${API_URL}/playlists/${id}/tracks`);
        if (res.ok) {
            const tracks = await res.json();
            list.innerHTML = '';
            if (tracks.length === 0) {
                list.innerHTML = '<li>No hay tracks descargados (o no se ha ejecutado aún).</li>';
            } else {
                tracks.forEach(track => {
                    const li = document.createElement('li');
                    li.textContent = track;
                    list.appendChild(li);
                });
            }
        } else {
            throw new Error();
        }
    } catch (e) {
        list.innerHTML = '<li style="color:var(--error)">Error cargando tracks.</li>';
    }
}

// Expose to window
window.viewTracks = viewTracks;

async function addPlaylist() {
    const nameEl = document.getElementById('pl-name');
    const urlEl = document.getElementById('pl-url');
    const name = nameEl.value;
    const url = urlEl.value;

    if (!name || !url) return;

    const id = "pl_" + Date.now(); // Simple ID generation
    const payload = { id, name, urls: [url] };

    try {
        await fetch(`${API_URL}/playlists`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        nameEl.value = '';
        urlEl.value = '';
        loadPlaylists();
    } catch (e) {
        alert("Error al añadir playlist");
    }
}

async function deletePlaylist(id) {
    if (!confirm("¿Seguro que quieres borrar esta playlist?")) return;
    try {
        await fetch(`${API_URL}/playlists/${id}`, { method: 'DELETE' });
        loadPlaylists();
    } catch (e) {
        alert("Error al borrar");
    }
}

// WebSocket
let socket;
let reconnectTimer;

function connectWS() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("WS Connected");
        setOnline(true);
        if (reconnectTimer) clearInterval(reconnectTimer);
    };

    socket.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'status') updateStatusUI(msg.data);
            if (msg.type === 'log') appendLog(msg.data);
        } catch (e) { console.error("WS Parse Error", e); }
    };

    socket.onclose = () => {
        console.log("WS Disconnected");
        setOnline(false);
        // Try reconnect
        reconnectTimer = setTimeout(connectWS, 3000);
    };
}

// UI Updaters
function updateStatusUI(data) {
    const container = document.getElementById('status-container');
    const stateBadge = document.getElementById('status-state');
    const progressBar = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-percent');

    // Show container if active
    if (data.state !== 'idle') {
        container.style.display = 'block';
    }

    // Map states
    const statusMap = {
        'idle': 'Inactivo',
        'starting': 'Iniciando...',
        'processing': 'Procesando...',
        'downloading': 'Descargando',
        'retrying': 'Reintentando (Límite API)',
        'error': 'Error'
    };

    stateBadge.textContent = statusMap[data.state] || data.state;

    // Progress
    let percent = 0;
    if (data.total_songs > 0) {
        percent = Math.round((data.downloaded / data.total_songs) * 100);
    }
    progressBar.style.width = `${percent}%`;
    progressText.textContent = `${percent}%`;

    document.getElementById('status-downloaded').textContent = data.downloaded;
    document.getElementById('status-total-count').textContent = data.total_songs;

    // Song Info
    const songEl = document.getElementById('status-song');
    if (data.current_song) {
        songEl.textContent = data.current_song;
    }

    // Completion Check
    if (data.state === 'idle' && percent === 100 && data.total_songs > 0) {
        stateBadge.textContent = 'Finalizado';
        stateBadge.style.background = 'rgba(16, 185, 129, 0.2)';
        stateBadge.style.color = 'var(--success)';
        // Optional: Hide after delay, but user might want to see logs
    }
}

function appendLog(text) {
    const consoleBox = document.getElementById('console-logs');
    const div = document.createElement('div');
    div.className = 'log-line log-dim'; // Default style

    // ANSI color parsing (basic)
    // 92m = Green, 96m = Cyan, 93m = Yellow, 91m = Red, 0m = Reset
    if (text.includes('\u001b[92m')) div.className = 'log-line log-green';
    else if (text.includes('\u001b[96m')) div.className = 'log-line log-cyan';
    else if (text.includes('\u001b[93m')) div.className = 'log-line log-yellow';
    else if (text.includes('\u001b[91m')) div.className = 'log-line log-red';

    // Strip codes for clean text
    // eslint-disable-next-line no-control-regex
    const cleanText = text.replace(/\u001b\[\d+m/g, '');
    div.textContent = `> ${cleanText}`;

    consoleBox.appendChild(div);
    consoleBox.scrollTop = consoleBox.scrollHeight;
}

// Run
async function runNow() {
    const btn = document.getElementById('btn-download');

    // Reset UI
    document.getElementById('status-container').style.display = 'block';
    document.getElementById('console-logs').innerHTML = '';
    document.getElementById('progress-fill').style.width = '0%';
    document.getElementById('status-state').textContent = 'Solicitando...';

    try {
        btn.disabled = true;
        await fetch(`${API_URL}/run`, { method: 'POST' });
        // The WS will take over from here
    } catch (e) {
        alert("Error de conexión al iniciar");
        btn.disabled = false;
    }

    // Re-enable button after a bit just in case, or listen to idle state
    setTimeout(() => btn.disabled = false, 2000);
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    loadPlaylists();
    connectWS();

    document.getElementById('btn-save-config').onclick = saveConfig;
    document.getElementById('btn-add-pl').onclick = addPlaylist;
    document.getElementById('btn-download').onclick = runNow;

    document.getElementById('btn-clear-console').onclick = () => {
        document.getElementById('console-logs').innerHTML = '';
    };
});

// Expose delete to window for onclick
window.deletePlaylist = deletePlaylist;

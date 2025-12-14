import { API } from './js/api.js';
import { UI } from './js/ui.js';
import { WebSocketClient } from './js/ws.js';

const API_URL = "";
// Determine WS Protocol
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${protocol}//${window.location.host}/ws`;

const api = new API(API_URL);
const ui = new UI(api);

let currentEditId = null;

// === Event Handlers ===

async function loadConfig() {
    try {
        const data = await api.getConfig();
        ui.renderConfig(data);
        ui.setOnline(true);
    } catch (e) {
        ui.setOnline(false);
    }
}

async function saveConfig() {
    const btn = document.getElementById('btn-save-config');
    const outputDir = document.getElementById('conf-output').value;
    const concurrency = parseInt(document.getElementById('conf-concurrency').value);
    const format = document.getElementById('conf-format').value;
    const schedule = parseInt(document.getElementById('conf-schedule').value);

    try {
        btn.disabled = true;
        await api.saveConfig({
            output_dir: outputDir,
            concurrency: concurrency,
            format: format
        });

        // Save Schedule Separately (API separation)
        await api.setSchedule(schedule);

        ui.showToast("Configuración guardada", "success");
        loadConfig(); // Reload to confirm
    } catch (e) {
        ui.showToast("Error guardando configuración", "error");
    } finally {
        btn.disabled = false;
    }
}

async function loadHistory() {
    try {
        const data = await api.getHistory();
        ui.renderHistory(data);
    } catch (e) {
        console.error("History error", e);
    }
}

async function loadPlaylists() {
    try {
        const data = await api.getPlaylists();
        ui.renderPlaylists(data);
        attachPlaylistListeners(); // Re-attach events
    } catch (e) {
        attachPlaylistListeners();
    }
}

function attachPlaylistListeners() {
    // Delete
    document.querySelectorAll('.action-delete').forEach(btn => {
        btn.onclick = () => deletePlaylist(btn.dataset.id);
    });

    // View
    document.querySelectorAll('.action-view').forEach(btn => {
        btn.onclick = () => viewTracks(btn.dataset.id, btn.dataset.name);
    });

    // Sync Single
    document.querySelectorAll('.action-sync').forEach(btn => {
        btn.onclick = () => syncPlaylist(btn.dataset.id);
    });

    // Edit (NEW)
    const editBtns = document.querySelectorAll('.action-edit');
    console.log(`Found ${editBtns.length} edit buttons`);
    editBtns.forEach(btn => {
        btn.onclick = () => {
            console.log("Edit clicked for:", btn.dataset.id);
            openEditModal(btn.dataset.id);
        };
    });
}

async function addPlaylist() {
    const nameInput = document.getElementById('pl-name');
    const urlInput = document.getElementById('pl-url');
    const name = nameInput.value.trim();
    const url = urlInput.value.trim();

    if (!name || !url) {
        ui.showToast("Rellena nombre y URL", "warning");
        return;
    }

    const id = `pl_${Date.now()}`;
    const payload = {
        id: id,
        name: name,
        urls: [url]
    };

    try {
        await api.savePlaylist(payload);
        ui.showToast("Playlist creada", "success");
        nameInput.value = '';
        urlInput.value = '';
        loadPlaylists();
    } catch (e) {
        if (e.status === 422) {
            ui.showToast("Error: URL inválida", "error");
        } else {
            ui.showToast("Error creando playlist", "error");
        }
    }
}

async function deletePlaylist(id) {
    if (!confirm("¿Seguro que quieres borrar esta playlist?")) return;
    try {
        await api.deletePlaylist(id);
        ui.showToast("Playlist eliminada", "info");
        loadPlaylists();
    } catch (e) {
        ui.showToast("Error eliminando", "error");
    }
}

// === Edit Feature ===
async function openEditModal(id) {
    try {
        const playlists = await api.getPlaylists();
        const pl = playlists.find(p => p.id === id);
        if (!pl) {
            ui.showToast("No se encontró la playlist", "error");
            return;
        }

        currentEditId = id;
        const nameInput = document.getElementById('edit-name');
        const urlsInput = document.getElementById('edit-urls');
        const modal = document.getElementById('edit-modal');

        if (!nameInput || !urlsInput || !modal) return;

        nameInput.value = pl.name;
        urlsInput.value = pl.urls.join('\n');

        modal.style.display = 'flex';

        // Close handler
        modal.querySelector('.close-edit').onclick = () => {
            modal.style.display = 'none';
            currentEditId = null;
        };

        // Save handler
        document.getElementById('btn-save-edit').onclick = saveEditPlaylist;

    } catch (e) {
        console.error("Error inside openEditModal:", e);
        ui.showToast("Error cargando datos", "error");
    }
}

async function saveEditPlaylist() {
    if (!currentEditId) return;

    const name = document.getElementById('edit-name').value.trim();
    const urlsText = document.getElementById('edit-urls').value.trim();
    const urls = urlsText.split('\n').map(u => u.trim()).filter(u => u.length > 0);

    if (!name || urls.length === 0) {
        ui.showToast("Nombre y URLs requeridos", "warning");
        return;
    }

    try {
        await api.savePlaylist({
            id: currentEditId,
            name: name,
            urls: urls
        });

        ui.showToast("Playlist actualizada", "success");
        document.getElementById('edit-modal').style.display = 'none';
        currentEditId = null;
        loadPlaylists();
    } catch (e) {
        if (e.status === 422) {
            ui.showToast("Error: URL inválida", "error");
        } else {
            ui.showToast("Error al guardar", "error");
        }
    }
}

async function syncPlaylist(id) {
    try {
        await api.syncPlaylist(id);
        ui.showToast("Sincronización iniciada", "info");
        // Switch to Dashboard to see progress
        showTab('dashboard');
    } catch (e) {
        ui.showToast("Error al iniciar sincronización", "error");
    }
}

async function viewTracks(id, name) {
    const modal = document.getElementById('tracks-modal');
    const title = document.getElementById('modal-title');
    const list = document.getElementById('tracks-list');

    title.textContent = `Tracks: ${name}`;
    list.innerHTML = '<li class="loading-state">Cargando...</li>';
    modal.style.display = 'flex'; // Use flex for centering (via CSS)

    try {
        const tracks = await api.getTracks(id);
        list.innerHTML = '';
        if (tracks.length === 0) {
            list.innerHTML = '<li class="empty-state">No hay tracks descargados.</li>';
        } else {
            tracks.forEach(track => {
                const li = document.createElement('li');
                li.className = 'track-item';

                // Cleanup filename: remove leading ./ and extension
                let cleanName = track.replace(/^\.\//, ''); // Remove ./
                cleanName = cleanName.replace(/\.(opus|mp3|m4a|flac)$/, ''); // Remove ext

                li.innerHTML = `
                    <span class="track-icon">🎵</span>
                    <span class="track-name">${cleanName}</span>
                `;
                list.appendChild(li);
            });
        }
    } catch (e) {
        list.innerHTML = '<li class="error-state">Error cargando tracks.</li>';
    }
}

async function runNow() {
    const btn = document.getElementById('btn-download');
    // Reset UI via simplified manual reset or add method to UI
    document.getElementById('status-container').style.display = 'block';

    try {
        btn.disabled = true;
        await api.runNow();
        ui.showToast("Sincronización Global Iniciada", "success");
    } catch (e) {
        ui.showToast("Error de conexión", "error");
        btn.disabled = false;
    }
    setTimeout(() => btn.disabled = false, 2000);
}

async function stopJob() {
    const btn = document.getElementById('btn-stop');
    try {
        btn.disabled = true;
        await api.stop();
        ui.showToast("Deteniendo...", "warning");
    } catch (e) {
        ui.showToast("Error al detener", "error");
        btn.disabled = false;
    }
}

// === TABS ===
function showTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');

    document.getElementById(`tab-btn-${tabId}`).classList.add('active');
    document.getElementById(`tab-${tabId}`).style.display = 'block';

    if (tabId === 'history') loadHistory();
}

// === Init ===

document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    loadPlaylists();

    const ws = new WebSocketClient(WS_URL, {
        onOpen: () => ui.setOnline(true),
        onClose: () => ui.setOnline(false),
        onMessage: (msg) => {
            if (msg.type === 'status') ui.updateStatus(msg.data);
            if (msg.type === 'log') ui.appendLog(msg.data);
        }
    });
    ws.connect();

    // Global buttons
    document.getElementById('btn-save-config').onclick = saveConfig;
    document.getElementById('btn-add-pl').onclick = addPlaylist;
    document.getElementById('btn-download').onclick = runNow;
    document.getElementById('btn-stop').onclick = stopJob;
    document.getElementById('btn-clear-console').onclick = () => {
        document.getElementById('console-logs').innerHTML = '';
    };

    // Tabs 
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.onclick = () => showTab(btn.dataset.tab);
    });

    // Default Tab
    showTab('dashboard');

    // Modal Close
    window.onclick = (event) => {
        const modal = document.getElementById('tracks-modal');
        if (event.target == modal) {
            modal.style.display = "none";
        }
    }
    document.querySelector('.close').onclick = () => {
        document.getElementById('tracks-modal').style.display = "none";
    }
});

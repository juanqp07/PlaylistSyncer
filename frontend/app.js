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
        document.getElementById('conf-bitrate').value = data.bitrate || "128k";
        document.getElementById('conf-lyrics').value = data.lyrics_provider || "genius";

        if (data.env_auth_set) {
            const idInput = document.getElementById('conf-client-id');
            const secInput = document.getElementById('conf-client-secret');

            idInput.value = "********";
            idInput.disabled = true;
            idInput.title = "Configurado por variable de entorno (.env)";

            secInput.value = "********";
            secInput.disabled = true;
            secInput.title = "Configurado por variable de entorno (.env)";
        } else {
            document.getElementById('conf-client-id').value = data.spotify_client_id || "";
            document.getElementById('conf-client-secret').value = data.spotify_client_secret || "";
        }

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
        bitrate: document.getElementById('conf-bitrate').value,
        lyrics_provider: document.getElementById('conf-lyrics').value,
        spotify_client_id: document.getElementById('conf-client-id').value,
        spotify_client_secret: document.getElementById('conf-client-secret').value,
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
                     <button class="btn btn-secondary" onclick="viewTracks('${pl.id}', '${pl.name}')">Ver Tracks</button>
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

// Run
async function runNow() {
    const btn = document.getElementById('btn-run');
    const status = document.getElementById('run-status');
    try {
        btn.disabled = true;
        await fetch(`${API_URL}/run`, { method: 'POST' });
        status.textContent = "Ejecución iniciada en background...";
        status.style.color = "var(--success)";
    } catch (e) {
        status.textContent = "Error de conexión";
        status.style.color = "var(--error)";
    } finally {
        setTimeout(() => {
            btn.disabled = false;
            status.textContent = "";
        }, 5000);
    }
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    loadPlaylists();

    document.getElementById('btn-save-config').onclick = saveConfig;
    document.getElementById('btn-add-pl').onclick = addPlaylist;
    document.getElementById('btn-run').onclick = runNow;
});

// Expose delete to window for onclick
window.deletePlaylist = deletePlaylist;

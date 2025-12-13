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

// Run
async function runNow() {
    const btn = document.getElementById('btn-download');
    const status = document.getElementById('run-status');

    // Show status container immediately
    document.getElementById('status-container').style.display = 'block';

    let hasStarted = false;
    let attempts = 0;

    // Start polling status
    const pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_URL}/status`);
            const data = await res.json();

            const statusMap = {
                'idle': 'Inactivo',
                'starting': 'Iniciando...',
                'processing': 'Procesando...',
                'downloading': 'Descargando',
                'retrying': 'Reintentando (Límite API)',
                'error': 'Error'
            };

            document.getElementById('status-state').textContent = statusMap[data.state] || data.state;
            document.getElementById('status-song').textContent = data.current_song || "-";
            // Show progress: 10 / 150
            document.getElementById('status-total').textContent = `${data.downloaded} / ${data.total_songs || "?"}`;

            // Check if process has started
            if (data.state !== 'idle') {
                hasStarted = true;
                // Clear "Request sent" message once we see movement
                if (status.textContent === "Solicitud enviada...") {
                    status.textContent = "";
                }
            }

            attempts++;

            // Completion logic
            // If we have started seeing activity, and now it is idle again -> Finished
            if (hasStarted && data.state === 'idle') {
                clearInterval(pollInterval);
                btn.disabled = false;

                // Update header
                status.textContent = "¡Completado! 🎉";
                status.style.color = "var(--success)";
                document.getElementById('status-state').textContent = "Finalizado";

                // Clear stats details as requested to avoid "Actual: -" ugliness
                document.getElementById('status-song').parentElement.style.opacity = '0.3';
                document.getElementById('status-song').textContent = "-";

                setTimeout(() => {
                    status.textContent = "";
                    document.getElementById('status-container').style.display = 'none'; // Hide entirely after a while
                    document.getElementById('status-song').parentElement.style.opacity = '1'; // Reset for next time
                }, 5000);
            }

            // Safety: if 10 seconds passed and still idle, assume it failed to start or finished instantly
            if (!hasStarted && attempts > 20) { // 20 * 0.5s = 10s
                clearInterval(pollInterval);
                btn.disabled = false;
                status.textContent = "No se detectó actividad (o finalizó muy rápido).";
                setTimeout(() => status.textContent = "", 5000);
            }

        } catch (e) { console.error(e); }
    }, 500);

    try {
        btn.disabled = true;

        // Trigger run
        await fetch(`${API_URL}/run`, { method: 'POST' });

        status.textContent = "Solicitud enviada...";
        status.style.color = "var(--success)";
    } catch (e) {
        status.textContent = "Error de conexión";
        status.style.color = "var(--error)";
        // Cleanup if request itself failed
        clearInterval(pollInterval);
        btn.disabled = false;
    }
    // Do NOT clear interval in finally
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    loadPlaylists();

    document.getElementById('btn-save-config').onclick = saveConfig;
    document.getElementById('btn-add-pl').onclick = addPlaylist;
    document.getElementById('btn-download').onclick = runNow;
});

// Expose delete to window for onclick
window.deletePlaylist = deletePlaylist;

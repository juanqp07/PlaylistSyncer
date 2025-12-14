
export class UI {
    constructor(api) {
        this.api = api;
        this.consoleLogs = []; // Internal buffer if needed, asking app.js to handle logic mainly
        this.toastContainer = document.getElementById('toast-container');
    }

    showToast(msg, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = msg;
        this.toastContainer.appendChild(toast);

        // Appear
        requestAnimationFrame(() => toast.style.opacity = '1');

        // Remove after 3s
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    setOnline(isOnline) {
        const el = document.getElementById('status-indicator');
        if (isOnline) {
            el.textContent = 'Conectado';
            el.style.color = 'var(--success)';
            el.style.borderColor = 'var(--success)';
        } else {
            el.textContent = 'Desconectado';
            el.style.color = 'var(--error)';
            el.style.borderColor = 'var(--error)';
        }
    }

    renderConfig(data) {
        const outInput = document.getElementById('conf-output');
        outInput.value = data.output_dir || "";

        if (data.is_docker) {
            outInput.disabled = true;
            outInput.title = "Gestionado por Docker (Volumen)";
            outInput.parentElement.style.display = 'none';
        }
        // concurrency removed
        document.getElementById('conf-format').value = data.format || "opus";
        document.getElementById('conf-schedule').value = data.schedule_interval_hours || 0;

        if (data.version) {
            document.getElementById('app-version').textContent = `v${data.version}`;
        }
    }

    renderPlaylists(data) {
        const list = document.getElementById('playlist-list');
        list.innerHTML = '';
        data.forEach(pl => {
            const item = document.createElement('div');
            item.className = 'list-item';
            // Explicitly escape single quotes for onclick just in case, though API handles objects better ideally
            // passing IDs to a global handler or event listener is better, but keeping onclick for compatibility
            // actually "viewTracks" and "deletePlaylist" need to be globally accessible or attached here.

            // We'll trust the main Glue code to expose them or we attach listeners.
            // Let's use data attributes for cleaner event handling in main.

            const countBadge = (pl.track_count !== undefined)
                ? `<span class="badge info">${pl.track_count} 🎵</span>`
                : `<span class="badge warning">Sin sinc.</span>`;

            item.innerHTML = `
                <div class="pl-info">
                    <strong>${pl.name}</strong>
                    <div class="meta">
                        ${countBadge}
                        <span class="url-preview">${new URL(pl.urls[0]).hostname}</span>
                    </div>
                </div>
                <div class="actions">
                     <button class="btn btn-icon action-sync" title="Sincronizar ahora" data-id="${pl.id}">🔄</button>
                     <button class="btn btn-info action-edit" title="Editar" data-id="${pl.id}" style="padding: 0 10px;">✏️</button>
                     <button class="btn btn-secondary action-view" data-id="${pl.id}" data-name="${pl.name.replace(/"/g, '&quot;')}">Listar</button>
                     <button class="btn btn-danger action-delete" data-id="${pl.id}">🗑</button>
                </div>
            `;
            list.appendChild(item);
        });
    }

    renderHistory(data) {
        const list = document.getElementById('history-list');
        list.innerHTML = '';
        if (!data || data.length === 0) {
            list.innerHTML = '<div class="empty-state">No hay historial reciente.</div>';
            return;
        }

        data.forEach(entry => {
            const item = document.createElement('div');
            item.className = 'history-item';

            // Format time 
            const date = new Date(entry.created_at + "Z"); // Assume UTC DB
            const timeAgo = this.timeAgo(date);
            const duration = Math.round(entry.duration_seconds);

            item.innerHTML = `
                <div class="h-header">
                    <strong>${entry.playlist_name}</strong>
                    <span class="h-time">${timeAgo}</span>
                </div>
                <div class="h-details">
                    <span>${entry.items_downloaded} / ${entry.total_items} items</span>
                    <span>⏱ ${duration}s</span>
                </div>
            `;
            list.appendChild(item);
        });
    }

    timeAgo(date) {
        const seconds = Math.floor((new Date() - date) / 1000);
        let interval = seconds / 31536000;
        if (interval > 1) return Math.floor(interval) + " años";
        interval = seconds / 2592000;
        if (interval > 1) return Math.floor(interval) + " meses";
        interval = seconds / 86400;
        if (interval > 1) return Math.floor(interval) + " días";
        interval = seconds / 3600;
        if (interval > 1) return Math.floor(interval) + "h";
        interval = seconds / 60;
        if (interval > 1) return Math.floor(interval) + "min";
        return Math.floor(seconds) + "s";
    }

    updateStatus(data) {
        const container = document.getElementById('status-container');
        const stateBadge = document.getElementById('status-state');
        const progressBar = document.getElementById('progress-fill');
        const progressText = document.getElementById('progress-percent');
        const btnStop = document.getElementById('btn-stop');
        const btnClear = document.getElementById('btn-clear-console');

        // Explicit active states
        const activeStates = ['starting', 'processing', 'downloading', 'retrying'];
        const isRunning = activeStates.includes(data.state);

        const actionsContainer = document.querySelector('.actions');
        if (actionsContainer) {
            if (isRunning) actionsContainer.classList.add('running');
            else actionsContainer.classList.remove('running');
        }

        if (isRunning) {
            container.style.display = 'block';
            if (btnStop) {
                btnStop.style.display = 'inline-flex';
                btnStop.disabled = false;
            }
            if (btnClear) {
                btnClear.style.display = 'inline-flex';
            }
        } else {
            if (btnStop) btnStop.style.display = 'none';
            if (btnClear) btnClear.style.display = 'none';
        }

        const statusMap = {
            'idle': 'En espera...',
            'starting': 'Iniciando...',
            'processing': 'Procesando...',
            'downloading': 'Descargando',
            'retrying': 'Reintentando API...',
            'error': 'Error'
        };

        stateBadge.textContent = statusMap[data.state] || data.state;
        stateBadge.className = 'status-badge';

        if (data.state === 'downloading') {
            stateBadge.style.background = 'rgba(139, 92, 246, 0.2)';
            stateBadge.style.color = '#d8b4fe';
            stateBadge.style.borderColor = 'rgba(139, 92, 246, 0.3)';
        } else if (data.state === 'idle') {
            stateBadge.style.background = 'rgba(255, 255, 255, 0.05)';
            stateBadge.style.color = 'var(--text-muted)';
            stateBadge.style.borderColor = 'var(--card-border)';
        }

        let percent = 0;
        if (data.total_songs > 0) {
            percent = Math.round((data.downloaded / data.total_songs) * 100);
        }

        if (data.state === 'idle' && data.total_songs === 0) {
            progressBar.style.width = '0%';
            progressText.textContent = '--%';
            document.getElementById('status-downloaded').textContent = '-';
            document.getElementById('status-total-count').textContent = '-';
        } else {
            progressBar.style.width = `${percent}%`;
            progressText.textContent = `${percent}%`;
            document.getElementById('status-downloaded').textContent = data.downloaded;
            document.getElementById('status-total-count').textContent = data.total_songs;
        }

        const songEl = document.getElementById('status-song');
        const plLabel = document.getElementById('status-playlist-label');

        if (data.playlist_name && data.state !== 'idle') {
            plLabel.textContent = `[${data.playlist_name}] `;
            plLabel.style.display = 'inline';
        } else {
            plLabel.style.display = 'none';
        }

        if (data.state === 'idle') {
            songEl.textContent = 'Cola vacía';
            songEl.style.color = 'var(--text-muted)';
        } else if (data.current_song) {
            songEl.textContent = data.current_song;
            songEl.style.color = 'var(--text-main)';
        }

        if (data.state === 'idle' && percent === 100 && data.total_songs > 0) {
            stateBadge.textContent = 'Sincronizado';
            stateBadge.classList.add('online');
        }
    }

    appendLog(text) {
        const consoleBox = document.getElementById('console-logs');

        // eslint-disable-next-line no-control-regex
        const cleanText = text.replace(/\u001b\[\d+m/g, '').trim();

        const lastLog = consoleBox.lastElementChild;
        if (lastLog) {
            const lastText = lastLog.dataset.rawText;
            if (lastText === cleanText) {
                let count = parseInt(lastLog.dataset.repeat || 1) + 1;
                lastLog.dataset.repeat = count;
                let badge = lastLog.querySelector('.log-count');
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'log-count';
                    lastLog.appendChild(badge);
                }
                badge.textContent = `x${count}`;
                return;
            }
        }

        const div = document.createElement('div');
        div.className = 'log-line';
        div.dataset.rawText = cleanText;

        if (text.includes('\u001b[92m')) div.classList.add('log-green');
        else if (text.includes('\u001b[96m')) div.classList.add('log-cyan');
        else if (text.includes('\u001b[93m')) div.classList.add('log-yellow');
        else if (text.includes('\u001b[91m')) div.classList.add('log-red');

        if (cleanText.includes('RATE LIMIT')) {
            div.classList.add('log-warning-box');
            div.innerHTML = `<span>⚠️ ${cleanText}</span>`;
        } else if (cleanText.includes('Total Songs') || cleanText.includes('TOTAL ENCONTRADO')) {
            div.classList.add('log-info-box');
            div.textContent = `> ${cleanText}`;
        } else if (cleanText.includes('Descargando') || cleanText.includes('INICIANDO')) {
            div.textContent = `> ${cleanText}`;
        } else {
            if (!div.className.includes('log-')) div.classList.add('log-dim');
            div.textContent = `> ${cleanText}`;
        }

        consoleBox.appendChild(div);

        if (consoleBox.children.length > 500) {
            consoleBox.removeChild(consoleBox.firstElementChild);
        }

        consoleBox.scrollTop = consoleBox.scrollHeight;
    }
}

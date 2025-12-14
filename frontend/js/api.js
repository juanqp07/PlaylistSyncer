
export class API {
    constructor(baseUrl = "") {
        this.baseUrl = baseUrl;
    }

    async getConfig() {
        const res = await fetch(`${this.baseUrl}/config`);
        if (!res.ok) throw new Error("Failed to load config");
        return await res.json();
    }

    async saveConfig(payload) {
        const res = await fetch(`${this.baseUrl}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error("Failed to save config");
        return await res.json();
    }

    async getPlaylists() {
        const res = await fetch(`${this.baseUrl}/playlists`);
        return await res.json();
    }

    async savePlaylist(payload) {
        await fetch(`${this.baseUrl}/playlists`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    }

    async deletePlaylist(id) {
        await fetch(`${this.baseUrl}/playlists/${id}`, { method: 'DELETE' });
    }

    async getTracks(id) {
        const res = await fetch(`${this.baseUrl}/playlists/${id}/tracks`);
        if (!res.ok) throw new Error("Failed to load tracks");
        return await res.json();
    }

    async syncPlaylist(id) {
        await fetch(`${this.baseUrl}/playlists/${id}/sync`, { method: 'POST' });
    }

    async getHistory() {
        const res = await fetch(`${this.baseUrl}/history`);
        return await res.json();
    }

    async runNow() {
        await fetch(`${this.baseUrl}/run`, { method: 'POST' });
    }

    async stop() {
        const res = await fetch(`${this.baseUrl}/stop`, { method: 'POST' });
        if (!res.ok) throw new Error("Failed to stop");
        return await res.json();
    }

    async setSchedule(hours) {
        const res = await fetch(`${this.baseUrl}/schedule`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ interval_hours: parseInt(hours) })
        });
        if (!res.ok) throw new Error("Failed to set schedule");
        return await res.json();
    }

    async sanitize() {
        const res = await fetch(`${this.baseUrl}/api/sanitize`, { method: 'POST' });
        if (!res.ok) throw new Error("Failed to sanitize files");
        return await res.json();
    }
}

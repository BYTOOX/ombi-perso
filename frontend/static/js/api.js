/**
 * Plex Kiosk - API Client
 */

const API_BASE = '/api/v1';

class ApiClient {
    constructor() {
        this.token = localStorage.getItem('token');
    }

    setToken(token) {
        this.token = token;
        if (token) {
            localStorage.setItem('token', token);
        } else {
            localStorage.removeItem('token');
        }
    }

    async request(endpoint, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        const response = await fetch(`${API_BASE}${endpoint}`, {
            ...options,
            headers
        });

        if (response.status === 401) {
            this.setToken(null);
            window.location.reload();
            throw new Error('Session expirée');
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Erreur serveur' }));
            throw new Error(error.detail || 'Erreur');
        }

        return response.json();
    }

    // Auth
    async login(username, password) {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Erreur de connexion' }));
            throw new Error(error.detail);
        }

        const data = await response.json();
        this.setToken(data.access_token);
        return data;
    }

    async register(username, email, password) {
        const data = await this.request('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, email, password })
        });
        this.setToken(data.access_token);
        return data;
    }

    async loginWithPlex(plexToken) {
        const data = await this.request('/auth/plex', {
            method: 'POST',
            body: JSON.stringify({ plex_token: plexToken })
        });
        this.setToken(data.access_token);
        return data;
    }

    async getMe() {
        return this.request('/auth/me');
    }

    // Search
    async search(query, type = 'all', year = null, page = 1) {
        let url = `/search?q=${encodeURIComponent(query)}&type=${type}&page=${page}`;
        if (year) url += `&year=${year}`;
        return this.request(url);
    }

    async getMediaDetails(source, mediaId, mediaType) {
        return this.request(`/search/${source}/${mediaId}?media_type=${mediaType}`);
    }

    // Requests
    async createRequest(mediaData) {
        return this.request('/requests', {
            method: 'POST',
            body: JSON.stringify(mediaData)
        });
    }

    async getRequests(status = null, page = 1) {
        let url = `/requests?page=${page}`;
        if (status) url += `&status=${status}`;
        return this.request(url);
    }

    async getRequestStats() {
        return this.request('/requests/stats');
    }

    async cancelRequest(requestId) {
        return this.request(`/requests/${requestId}`, { method: 'DELETE' });
    }

    // Admin
    async getUsers() {
        return this.request('/admin/users');
    }

    async updateUser(userId, data) {
        return this.request(`/admin/users/${userId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    async getStats() {
        return this.request('/admin/stats');
    }

    async getHealth() {
        return this.request('/admin/health');
    }

    async scanLibrary() {
        return this.request('/admin/scan-library', { method: 'POST' });
    }
}

// Export singleton
window.api = new ApiClient();

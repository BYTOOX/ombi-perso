/**
 * Plex Kiosk - Main Application
 * Alpine.js powered SPA
 */

function app() {
    return {
        // App state
        appName: 'Plex Kiosk',
        view: 'home',

        // User state
        user: null,
        stats: { requests_remaining: 0 },

        // Search state
        searchQuery: '',
        searchResults: [],
        searching: false,
        mediaType: 'all',

        // Modal state
        showLoginModal: false,
        showRegisterModal: false,
        showMediaModal: false,
        selectedMedia: null,

        // Login form
        loginTab: 'local',
        loginForm: { username: '', password: '' },
        loginError: '',
        loggingIn: false,

        // Request state
        requestingMedia: false,

        // Toast
        toast: { show: false, message: '', type: 'info' },

        // Initialize
        async init() {
            // Load API client
            if (!window.api) {
                console.error('API client not loaded');
                return;
            }

            // Check if logged in
            const token = localStorage.getItem('token');
            if (token) {
                try {
                    this.user = await api.getMe();
                    await this.loadStats();
                } catch (e) {
                    console.error('Session expired');
                    localStorage.removeItem('token');
                }
            }

            // Watch media type changes
            this.$watch('mediaType', () => {
                if (this.searchQuery) this.search();
            });
        },

        // Search
        async search() {
            if (!this.searchQuery || this.searchQuery.length < 2) {
                this.searchResults = [];
                return;
            }

            this.searching = true;

            try {
                this.searchResults = await api.search(
                    this.searchQuery,
                    this.mediaType
                );
            } catch (e) {
                this.showToast('Erreur de recherche', 'error');
                console.error(e);
            } finally {
                this.searching = false;
            }
        },

        // Login
        async login() {
            this.loginError = '';
            this.loggingIn = true;

            try {
                const data = await api.login(
                    this.loginForm.username,
                    this.loginForm.password
                );
                this.user = data.user;
                this.showLoginModal = false;
                this.loginForm = { username: '', password: '' };
                await this.loadStats();
                this.showToast('Connecté !', 'success');
            } catch (e) {
                this.loginError = e.message;
            } finally {
                this.loggingIn = false;
            }
        },

        // Plex login
        async loginWithPlex() {
            // Open Plex OAuth window
            const clientId = 'plex-kiosk-' + Math.random().toString(36).substr(2, 9);
            const plexAuthUrl = `https://app.plex.tv/auth#?clientID=${clientId}&code=&context%5Bdevice%5D%5Bproduct%5D=Plex%20Kiosk`;

            const popup = window.open(plexAuthUrl, 'plex-auth', 'width=800,height=600');

            // Poll for token
            const checkAuth = setInterval(async () => {
                try {
                    // Check if auth completed
                    // This is a simplified version - real implementation needs Plex OAuth flow
                    if (popup.closed) {
                        clearInterval(checkAuth);
                    }
                } catch (e) {
                    // Cross-origin error expected while popup is on plex.tv
                }
            }, 1000);

            this.showToast('Connectez-vous dans la fenêtre Plex', 'info');
        },

        // Logout
        logout() {
            api.setToken(null);
            this.user = null;
            this.stats = { requests_remaining: 0 };
            this.showToast('Déconnecté', 'info');
        },

        // Load user stats
        async loadStats() {
            if (!this.user) return;

            try {
                this.stats = await api.getRequestStats();
            } catch (e) {
                console.error('Failed to load stats', e);
            }
        },

        // Open media modal
        async openMediaModal(media) {
            this.selectedMedia = media;
            this.showMediaModal = true;

            // Load full details
            try {
                const details = await api.getMediaDetails(
                    media.source,
                    media.id,
                    media.media_type
                );
                this.selectedMedia = { ...this.selectedMedia, ...details };
            } catch (e) {
                console.error('Failed to load details', e);
            }
        },

        // Request media
        async requestMedia() {
            if (!this.user || !this.selectedMedia) return;

            this.requestingMedia = true;

            try {
                // Determine media type for our backend
                let mediaType = this.selectedMedia.media_type;
                if (mediaType === 'anime') {
                    mediaType = 'anime';
                } else if (mediaType === 'series') {
                    mediaType = 'series';
                } else {
                    mediaType = 'movie';
                }

                await api.createRequest({
                    media_type: mediaType,
                    external_id: this.selectedMedia.id,
                    source: this.selectedMedia.source,
                    title: this.selectedMedia.title,
                    original_title: this.selectedMedia.original_title,
                    year: this.selectedMedia.year,
                    poster_url: this.selectedMedia.poster_url,
                    overview: this.selectedMedia.overview,
                    quality_preference: '1080p'
                });

                this.showMediaModal = false;
                this.showToast('Demande envoyée !', 'success');

                // Refresh stats
                await this.loadStats();

                // Mark as requested in results
                const index = this.searchResults.findIndex(
                    m => m.id === this.selectedMedia.id && m.source === this.selectedMedia.source
                );
                if (index >= 0) {
                    this.searchResults[index].already_available = true;
                }
            } catch (e) {
                this.showToast(e.message, 'error');
            } finally {
                this.requestingMedia = false;
            }
        },

        // Helpers
        getMediaTypeLabel(type) {
            const labels = {
                'movie': 'Film',
                'series': 'Série',
                'anime': 'Animé',
                'animated_movie': 'Film d\'animation',
                'animated_series_us': 'Série animée'
            };
            return labels[type] || type;
        },

        showToast(message, type = 'info') {
            this.toast = { show: true, message, type };
            setTimeout(() => {
                this.toast.show = false;
            }, 3000);
        }
    };
}

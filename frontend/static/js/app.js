/**
 * Plex Kiosk - Main Application
 * Netflix-style media browser with search and request functionality
 */

// =============================================================================
// Configuration
// =============================================================================
const API_BASE = '/api/v1';
const DEBOUNCE_DELAY = 300;
const ITEMS_PER_ROW = 20;

// =============================================================================
// State Management
// =============================================================================
const state = {
    user: null,
    authenticated: false,
    searchQuery: '',
    searchResults: [],
    searching: false,
    mediaType: 'all',
    selectedMedia: null,
    userStats: null,
    trending: {
        movies: [],
        series: [],
        anime: []
    }
};

// =============================================================================
// API Service
// =============================================================================
const api = {
    /**
     * Get authorization headers
     */
    getHeaders() {
        const token = localStorage.getItem('access_token');
        return {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` })
        };
    },

    /**
     * Make API request
     */
    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            ...options,
            headers: {
                ...this.getHeaders(),
                ...options.headers
            }
        };

        try {
            const response = await fetch(url, config);

            // Handle 401 - redirect to login
            if (response.status === 401) {
                localStorage.removeItem('access_token');
                localStorage.removeItem('user');
                window.location.href = '/login.html';
                return null;
            }

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'API Error');
            }

            return data;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    // Auth endpoints
    async getCurrentUser() {
        return this.request('/auth/me');
    },

    async getUserStats() {
        return this.request('/auth/stats');
    },

    async logout() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/login.html';
    },

    // Search endpoints
    async search(query, type = 'all') {
        const params = new URLSearchParams({ query });
        if (type !== 'all') {
            params.append('type', type);
        }
        return this.request(`/search?${params}`);
    },

    async getTrending(type = 'movie') {
        return this.request(`/search/trending?type=${type}`);
    },

    // Request endpoints
    async createRequest(mediaData) {
        return this.request('/requests', {
            method: 'POST',
            body: JSON.stringify(mediaData)
        });
    },

    async getMyRequests() {
        return this.request('/requests/me');
    },

    async cancelRequest(requestId) {
        return this.request(`/requests/${requestId}`, {
            method: 'DELETE'
        });
    }
};

// =============================================================================
// UI Components
// =============================================================================
const UI = {
    /**
     * Create media card HTML
     */
    createMediaCard(media) {
        const posterUrl = media.poster_url || '/static/img/no-poster.png';
        const rating = media.rating ? media.rating.toFixed(1) : null;
        const typeLabel = this.getMediaTypeLabel(media.media_type);

        return `
            <div class="media-card" data-media-id="${media.id}" data-media-source="${media.source || 'tmdb'}">
                <div class="media-poster">
                    <img src="${posterUrl}" alt="${media.title}" loading="lazy" 
                         onerror="this.src='/static/img/no-poster.png'">
                    ${rating ? `<span class="media-badge rating">⭐ ${rating}</span>` : ''}
                    ${media.already_available ? '<span class="media-badge available">Disponible</span>' : ''}
                    ${media.requested ? '<span class="media-badge requested">Demandé</span>' : ''}
                    <div class="media-overlay">
                        <div class="media-overlay-meta">
                            ${media.year || '—'} • ${typeLabel}
                        </div>
                        <div class="media-overlay-actions">
                            <button class="btn btn-primary btn-card btn-view-details">
                                <i class="bi bi-info-circle"></i> Détails
                            </button>
                        </div>
                    </div>
                </div>
                <div class="media-title">${media.title}</div>
                <div class="media-year">${media.year || ''}</div>
            </div>
        `;
    },

    /**
     * Create media row HTML
     */
    createMediaRow(title, icon, items, id) {
        if (!items || items.length === 0) return '';

        return `
            <section class="media-section" id="${id}">
                <div class="section-header">
                    <h2 class="section-title">
                        <i class="bi bi-${icon}"></i> ${title}
                    </h2>
                    <a href="#" class="section-link">
                        Tout voir <i class="bi bi-chevron-right"></i>
                    </a>
                </div>
                <div class="row-nav prev" onclick="scrollRow('${id}', -1)">
                    <i class="bi bi-chevron-left"></i>
                </div>
                <div class="media-row">
                    ${items.map(item => this.createMediaCard(item)).join('')}
                </div>
                <div class="row-nav next" onclick="scrollRow('${id}', 1)">
                    <i class="bi bi-chevron-right"></i>
                </div>
            </section>
        `;
    },

    /**
     * Get media type label
     */
    getMediaTypeLabel(type) {
        const labels = {
            'movie': 'Film',
            'series': 'Série',
            'tv': 'Série',
            'anime': 'Animé'
        };
        return labels[type] || type;
    },

    /**
     * Create hero section HTML
     */
    createHero(media) {
        if (!media) return '';

        const backdropUrl = media.backdrop_url || media.poster_url;
        const rating = media.rating ? media.rating.toFixed(1) : null;
        const typeLabel = this.getMediaTypeLabel(media.media_type);

        return `
            <section class="hero-section">
                <div class="hero-backdrop" style="background-image: url('${backdropUrl}')"></div>
                <div class="hero-gradient"></div>
                <div class="hero-content">
                    <span class="hero-badge">
                        <i class="bi bi-fire"></i> Tendance
                    </span>
                    <h1 class="hero-title">${media.title}</h1>
                    <div class="hero-meta">
                        <span>${media.year || '—'}</span>
                        <span>•</span>
                        <span>${typeLabel}</span>
                        ${rating ? `
                            <span>•</span>
                            <span class="hero-rating">⭐ ${rating}</span>
                        ` : ''}
                    </div>
                    <p class="hero-overview">${media.overview || ''}</p>
                    <div class="hero-actions">
                        ${media.already_available ? `
                            <button class="btn btn-success btn-hero" disabled>
                                <i class="bi bi-check-circle"></i> Disponible
                            </button>
                        ` : `
                            <button class="btn btn-primary btn-hero" onclick="openMediaModal(${JSON.stringify(media).replace(/"/g, '&quot;')})">
                                <i class="bi bi-plus-circle"></i> Demander
                            </button>
                        `}
                        <button class="btn btn-secondary btn-hero" onclick="openMediaModal(${JSON.stringify(media).replace(/"/g, '&quot;')})">
                            <i class="bi bi-info-circle"></i> Plus d'infos
                        </button>
                    </div>
                </div>
            </section>
        `;
    },

    /**
     * Create search results grid
     */
    createSearchResults(results) {
        if (results.length === 0) {
            return `
                <div class="empty-state">
                    <div class="empty-icon">🔍</div>
                    <h3 class="empty-title">Aucun résultat</h3>
                    <p class="empty-text">Essayez avec d'autres termes de recherche</p>
                </div>
            `;
        }

        return `
            <div class="search-results fade-in">
                <div class="results-header mb-4">
                    <span class="text-muted">${results.length} résultat(s) trouvé(s)</span>
                </div>
                <div class="results-grid">
                    ${results.map(item => this.createMediaCard(item)).join('')}
                </div>
            </div>
        `;
    },

    /**
     * Show toast notification
     */
    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const icons = {
            success: 'check-circle',
            danger: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };

        const toastId = `toast-${Date.now()}`;
        const toastHtml = `
            <div id="${toastId}" class="toast bg-${type}" role="alert" aria-live="assertive">
                <div class="toast-header">
                    <i class="bi bi-${icons[type]} me-2 text-${type}"></i>
                    <strong class="me-auto">Plex Kiosk</strong>
                    <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
                </div>
                <div class="toast-body">${message}</div>
            </div>
        `;

        container.insertAdjacentHTML('beforeend', toastHtml);
        const toastEl = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
        toast.show();

        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    }
};

// =============================================================================
// App Functions
// =============================================================================

/**
 * Initialize application
 */
async function initApp() {
    // Check authentication
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '/login.html';
        return;
    }

    try {
        // Get current user
        const user = await api.getCurrentUser();
        state.user = user;
        state.authenticated = true;

        // Update UI with user info
        updateUserUI();

        // Get user stats
        try {
            const stats = await api.getUserStats();
            state.userStats = stats;
            updateStatsUI();
        } catch (e) {
            console.log('Stats not available');
        }

        // Load trending content
        await loadTrendingContent();

        // Setup event listeners
        setupEventListeners();

    } catch (error) {
        console.error('Init error:', error);
        // Redirect to login if auth fails
        localStorage.removeItem('access_token');
        window.location.href = '/login.html';
    }
}

/**
 * Update user UI elements
 */
function updateUserUI() {
    const userName = document.getElementById('userName');
    const userAvatar = document.getElementById('userAvatar');

    if (userName && state.user) {
        userName.textContent = state.user.username;
    }

    if (userAvatar && state.user) {
        userAvatar.textContent = state.user.username.charAt(0).toUpperCase();
    }
}

/**
 * Update stats UI
 */
function updateStatsUI() {
    const userRequests = document.getElementById('userRequests');

    if (userRequests && state.userStats) {
        userRequests.textContent = `${state.userStats.requests_remaining || 0} demandes restantes`;
    }
}

/**
 * Load trending content
 */
async function loadTrendingContent() {
    const mainContent = document.getElementById('mainContent');
    if (!mainContent) return;

    mainContent.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary"></div></div>';

    try {
        // Load trending movies
        const trendingMovies = await api.getTrending('movie');
        state.trending.movies = trendingMovies?.results || [];

        // Load trending series
        const trendingSeries = await api.getTrending('tv');
        state.trending.series = trendingSeries?.results || [];

        // Render content
        let html = '';

        // Hero with featured movie
        if (state.trending.movies.length > 0) {
            const featured = state.trending.movies[0];
            html += UI.createHero(featured);
        }

        // Content rows
        html += '<div class="content-rows">';
        html += UI.createMediaRow('Films Populaires', 'film', state.trending.movies, 'movies-row');
        html += UI.createMediaRow('Séries Tendances', 'tv', state.trending.series, 'series-row');
        html += '</div>';

        mainContent.innerHTML = html;

        // Attach click handlers to cards
        attachCardClickHandlers();

    } catch (error) {
        console.error('Error loading trending:', error);
        mainContent.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">😕</div>
                <h3 class="empty-title">Erreur de chargement</h3>
                <p class="empty-text">Impossible de charger le contenu. Réessayez plus tard.</p>
                <button class="btn btn-primary" onclick="loadTrendingContent()">Réessayer</button>
            </div>
        `;
    }
}

/**
 * Perform search
 */
let searchTimeout = null;
async function performSearch(query, type = 'all') {
    if (searchTimeout) {
        clearTimeout(searchTimeout);
    }

    state.searchQuery = query;
    state.mediaType = type;

    const mainContent = document.getElementById('mainContent');
    const searchSpinner = document.getElementById('searchSpinner');

    if (!query || query.length < 2) {
        // Show trending content if query is empty
        loadTrendingContent();
        return;
    }

    searchTimeout = setTimeout(async () => {
        state.searching = true;
        if (searchSpinner) searchSpinner.classList.remove('d-none');

        try {
            const results = await api.search(query, type);
            state.searchResults = results?.results || [];

            if (mainContent) {
                mainContent.innerHTML = UI.createSearchResults(state.searchResults);
                attachCardClickHandlers();
            }

        } catch (error) {
            console.error('Search error:', error);
            UI.showToast('Erreur lors de la recherche', 'danger');
        } finally {
            state.searching = false;
            if (searchSpinner) searchSpinner.classList.add('d-none');
        }
    }, DEBOUNCE_DELAY);
}

/**
 * Scroll media row
 */
function scrollRow(rowId, direction) {
    const section = document.getElementById(rowId);
    if (!section) return;

    const row = section.querySelector('.media-row');
    const scrollAmount = 800;

    row.scrollBy({
        left: direction * scrollAmount,
        behavior: 'smooth'
    });
}

/**
 * Open media detail modal
 */
function openMediaModal(media) {
    state.selectedMedia = media;

    const modal = document.getElementById('mediaModal');
    if (!modal) return;

    const backdropUrl = media.backdrop_url || media.poster_url || '';
    const posterUrl = media.poster_url || '/static/img/no-poster.png';
    const rating = media.rating ? media.rating.toFixed(1) : null;
    const typeLabel = UI.getMediaTypeLabel(media.media_type);
    const genres = media.genres || [];

    // Update modal content
    document.getElementById('modalBackdrop').style.backgroundImage = `url('${backdropUrl}')`;
    document.getElementById('modalPoster').src = posterUrl;
    document.getElementById('modalTitle').textContent = media.title;
    document.getElementById('modalYear').textContent = media.year || '—';
    document.getElementById('modalType').textContent = typeLabel;
    document.getElementById('modalRating').innerHTML = rating ? `⭐ ${rating}` : '';
    document.getElementById('modalOverview').textContent = media.overview || 'Aucune description disponible.';

    // Genres
    const genresContainer = document.getElementById('modalGenres');
    genresContainer.innerHTML = genres.map(g =>
        `<span class="genre-tag">${g}</span>`
    ).join('');

    // Actions
    const actionsContainer = document.getElementById('modalActions');
    if (media.already_available) {
        actionsContainer.innerHTML = `
            <button class="btn btn-success" disabled>
                <i class="bi bi-check-circle"></i> Déjà disponible
            </button>
        `;
    } else if (media.requested) {
        actionsContainer.innerHTML = `
            <button class="btn btn-secondary" disabled>
                <i class="bi bi-clock"></i> Demande en cours
            </button>
        `;
    } else {
        actionsContainer.innerHTML = `
            <button class="btn btn-primary" id="requestBtn" onclick="requestMedia()">
                <i class="bi bi-plus-circle"></i> Demander
            </button>
        `;
    }

    // Show modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

/**
 * Request media
 */
async function requestMedia() {
    if (!state.selectedMedia) return;

    const requestBtn = document.getElementById('requestBtn');
    if (requestBtn) {
        requestBtn.disabled = true;
        requestBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Envoi...';
    }

    try {
        await api.createRequest({
            media_id: state.selectedMedia.id,
            media_type: state.selectedMedia.media_type,
            title: state.selectedMedia.title,
            year: state.selectedMedia.year,
            poster_url: state.selectedMedia.poster_url,
            source: state.selectedMedia.source || 'tmdb'
        });

        UI.showToast(`"${state.selectedMedia.title}" a été demandé avec succès!`, 'success');

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('mediaModal'));
        if (modal) modal.hide();

        // Mark as requested in local state
        state.selectedMedia.requested = true;

        // Refresh user stats
        try {
            const stats = await api.getUserStats();
            state.userStats = stats;
            updateStatsUI();
        } catch (e) { }

    } catch (error) {
        console.error('Request error:', error);
        UI.showToast('Erreur lors de la demande', 'danger');
    } finally {
        if (requestBtn) {
            requestBtn.disabled = false;
            requestBtn.innerHTML = '<i class="bi bi-plus-circle"></i> Demander';
        }
    }
}

/**
 * Attach click handlers to media cards
 */
function attachCardClickHandlers() {
    document.querySelectorAll('.media-card').forEach(card => {
        card.addEventListener('click', () => {
            const mediaId = card.dataset.mediaId;
            const source = card.dataset.mediaSource;

            // Find media in state
            let media = null;

            // Check search results
            media = state.searchResults.find(m =>
                String(m.id) === mediaId && (m.source || 'tmdb') === source
            );

            // Check trending
            if (!media) {
                media = [...state.trending.movies, ...state.trending.series, ...state.trending.anime]
                    .find(m => String(m.id) === mediaId);
            }

            if (media) {
                openMediaModal(media);
            }
        });
    });
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Search input
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            performSearch(e.target.value, state.mediaType);
        });

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchInput.value = '';
                performSearch('');
            }
        });
    }

    // Filter tabs
    document.querySelectorAll('.filter-tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');

            const type = e.target.dataset.type;
            state.mediaType = type;

            if (state.searchQuery) {
                performSearch(state.searchQuery, type);
            }
        });
    });

    // Logout
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            api.logout();
        });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Focus search on /
        if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
            e.preventDefault();
            const searchInput = document.getElementById('searchInput');
            if (searchInput) searchInput.focus();
        }
    });
}

/**
 * Handle logout
 */
function logout() {
    api.logout();
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', initApp);

// Export for global access
window.scrollRow = scrollRow;
window.openMediaModal = openMediaModal;
window.requestMedia = requestMedia;
window.logout = logout;

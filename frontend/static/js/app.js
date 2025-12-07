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
    currentCategory: 'movie', // movie, tv, anime
    selectedMedia: null,
    userStats: null,
    trending: {
        movies: [],
        series: [],
        anime: []
    },
    categoryContent: {
        hero: null,
        top_rated: [],
        classics: [],
        hidden_gems: [],
        random: [],
        cat1: [],
        cat2: [],
        cat3: [],
        cat4: []
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
        const params = new URLSearchParams({ q: query });
        if (type !== 'all') {
            params.append('type', type);
        }
        return this.request(`/search?${params}`);
    },

    async getTrending(type = 'movie') {
        return this.request(`/search/trending?type=${type}`);
    },

    async getDiscover(type = 'movie', category = 'top_rated') {
        return this.request(`/search/discover?type=${type}&category=${category}`);
    },

    async getHero(type = 'movie') {
        return this.request(`/search/hero?type=${type}`);
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
    },

    // Plex availability endpoints
    async getAvailability(mediaType, tmdbId) {
        return this.request(`/plex/availability/${mediaType}/${tmdbId}`);
    },

    async getSeasonsAvailability(tmdbId) {
        return this.request(`/plex/availability/seasons/${tmdbId}`);
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
     * Create media row HTML with modern navigation
     */
    createMediaRow(title, icon, items, id, type = 'movie') {
        if (!items || items.length === 0) return '';

        // Store items for gallery modal access
        if (!window.rowData) window.rowData = {};
        window.rowData[id] = { title, icon, items, type };

        return `
            <section class="media-section" id="${id}">
                <div class="section-header">
                    <h2 class="section-title">
                        <i class="bi bi-${icon}"></i> ${title}
                    </h2>
                    <a href="#" class="section-link" onclick="openGalleryModal('${id}'); return false;">
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
                <div class="scroll-indicators" id="${id}-indicators"></div>
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
     * Create search results grid - grouped by type for better organization
     */
    createSearchResults(results, activeFilter = 'all') {
        if (results.length === 0) {
            return `
                <div class="empty-state">
                    <div class="empty-icon">🔍</div>
                    <h3 class="empty-title">Aucun résultat</h3>
                    <p class="empty-text">Essayez avec d'autres termes de recherche</p>
                </div>
            `;
        }

        // If a specific type is selected, show flat grid with that type only
        if (activeFilter !== 'all') {
            const filteredResults = results.filter(item => {
                if (activeFilter === 'movie') return item.media_type === 'movie';
                if (activeFilter === 'tv') return item.media_type === 'tv' || item.media_type === 'series';
                if (activeFilter === 'anime') return item.media_type === 'anime';
                return true;
            });

            return `
                <div class="search-results-modern fade-in">
                    <div class="results-header mb-4">
                        <span class="text-muted">${filteredResults.length} résultat(s) trouvé(s)</span>
                    </div>
                    <div class="results-mini-grid">
                        ${filteredResults.slice(0, 18).map(item => this.createMediaCardWithBadge(item)).join('')}
                    </div>
                </div>
            `;
        }

        // Group results by type for "all" filter
        const movies = results.filter(r => r.media_type === 'movie');
        const series = results.filter(r => r.media_type === 'tv' || r.media_type === 'series');
        const anime = results.filter(r => r.media_type === 'anime');

        let html = '<div class="search-results-modern fade-in">';
        html += `<div class="results-header mb-4"><span class="text-muted">${results.length} résultat(s) trouvé(s)</span></div>`;

        // Movies section
        if (movies.length > 0) {
            html += this.createResultSection('Films', 'film', movies, 'movie');
        }

        // Series section
        if (series.length > 0) {
            html += this.createResultSection('Séries', 'tv', series, 'tv');
        }

        // Anime section
        if (anime.length > 0) {
            html += this.createResultSection('Animés', 'stars', anime, 'anime');
        }

        html += '</div>';
        return html;
    },

    /**
     * Create a section for grouped search results
     */
    createResultSection(title, icon, items, type) {
        const maxVisible = 6;
        const visibleItems = items.slice(0, maxVisible);
        const hasMore = items.length > maxVisible;

        // Store for "voir plus" functionality
        if (!window.searchSections) window.searchSections = {};
        window.searchSections[type] = { title, icon, items };

        return `
            <div class="results-section">
                <div class="results-section-header">
                    <h3 class="results-section-title">
                        <i class="bi bi-${icon}"></i>
                        ${title}
                        <span class="results-section-count">${items.length}</span>
                    </h3>
                    ${hasMore ? `
                        <a href="#" class="results-expand" onclick="expandSearchSection('${type}'); return false;">
                            Voir plus <i class="bi bi-chevron-right"></i>
                        </a>
                    ` : ''}
                </div>
                <div class="results-mini-grid">
                    ${visibleItems.map(item => this.createMediaCardWithBadge(item)).join('')}
                </div>
            </div>
        `;
    },

    /**
     * Create media card with type badge
     */
    createMediaCardWithBadge(media) {
        const posterUrl = media.poster_url || '/static/img/no-poster.png';
        const rating = media.rating ? media.rating.toFixed(1) : null;
        const typeLabel = this.getMediaTypeLabel(media.media_type);
        const typeClass = media.media_type || 'movie';

        return `
            <div class="media-card" data-media-id="${media.id}" data-media-source="${media.source || 'tmdb'}">
                <div class="media-poster">
                    <span class="media-type-badge ${typeClass}">${typeLabel}</span>
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
 * Load category-based content (Films/Séries/Animés)
 */
async function loadCategoryContent(category = null) {
    const mainContent = document.getElementById('mainContent');
    if (!mainContent) return;

    // Use provided category or current state
    const type = category || state.currentCategory;
    state.currentCategory = type;

    // Update category pills UI
    document.querySelectorAll('.category-pill').forEach(pill => {
        pill.classList.toggle('active', pill.dataset.category === type);
    });

    mainContent.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary"></div></div>';

    try {
        // Fetch all content in parallel
        const [heroData, topRated, classics, hiddenGems, random, cat1, cat2, cat3, cat4] = await Promise.all([
            api.getHero(type),
            api.getDiscover(type, 'top_rated'),
            api.getDiscover(type, 'classics'),
            api.getDiscover(type, 'hidden_gems'),
            api.getDiscover(type, 'random'),
            // Category-specific tiles
            api.getDiscover(type, type === 'movie' ? 'blockbusters' : type === 'tv' ? 'binge' : 'shonen'),
            api.getDiscover(type, type === 'movie' ? 'comedy' : type === 'tv' ? 'airing' : 'romance'),
            api.getDiscover(type, type === 'movie' ? 'thriller' : type === 'tv' ? 'crime' : 'isekai'),
            api.getDiscover(type, type === 'movie' ? 'award_winners' : type === 'tv' ? 'miniseries' : 'psychological')
        ]);

        // Store in state
        state.categoryContent = {
            hero: heroData,
            top_rated: topRated?.results || [],
            classics: classics?.results || [],
            hidden_gems: hiddenGems?.results || [],
            random: random?.results || [],
            cat1: cat1?.results || [],
            cat2: cat2?.results || [],
            cat3: cat3?.results || [],
            cat4: cat4?.results || []
        };

        // Get category labels and specific tile configs
        const tileConfigs = {
            movie: {
                name: 'Films', icon: 'film',
                cat1: { title: '💥 Blockbusters', icon: 'fire' },
                cat2: { title: '😂 Comédies', icon: 'emoji-smile' },
                cat3: { title: '🌙 Frissons', icon: 'moon-stars' },
                cat4: { title: '🏆 Oscarisés', icon: 'award' }
            },
            tv: {
                name: 'Séries', icon: 'tv',
                cat1: { title: '📺 Binge-worthy', icon: 'play-circle' },
                cat2: { title: '🔥 En ce moment', icon: 'broadcast' },
                cat3: { title: '🕵️ Crime/Thriller', icon: 'search' },
                cat4: { title: '🎭 Dramas', icon: 'mask' }
            },
            anime: {
                name: 'Animés', icon: 'stars',
                cat1: { title: '⚔️ Shonen', icon: 'lightning' },
                cat2: { title: '💕 Romance', icon: 'heart' },
                cat3: { title: '🎮 Isekai/Fantasy', icon: 'controller' },
                cat4: { title: '🧠 Psychologique', icon: 'brain' }
            }
        };
        const config = tileConfigs[type] || tileConfigs.movie;

        // Render content
        let html = '';

        // Mini Hero
        if (state.categoryContent.hero) {
            html += createMiniHero(state.categoryContent.hero, config);
        }

        // Content sections as expandable tiles - 2 columns layout
        html += '<div class="content-tiles px-4">';
        html += '<div class="tiles-grid">';

        // Row 1: Top Rated + Category 1
        html += createExpandableTile('🏆 Meilleurs ' + config.name, 'trophy', state.categoryContent.top_rated, 'top-rated');
        html += createExpandableTile(config.cat1.title, config.cat1.icon, state.categoryContent.cat1, 'cat1');

        // Row 2: Classics + Category 2
        html += createExpandableTile('🎬 ' + config.name + ' Cultes', 'film', state.categoryContent.classics, 'classics');
        html += createExpandableTile(config.cat2.title, config.cat2.icon, state.categoryContent.cat2, 'cat2');

        // Row 3: Hidden Gems + Category 3
        html += createExpandableTile('💎 Pépites Cachées', 'gem', state.categoryContent.hidden_gems, 'hidden-gems');
        html += createExpandableTile(config.cat3.title, config.cat3.icon, state.categoryContent.cat3, 'cat3');

        // Row 4: Random + Category 4
        html += createExpandableTile('🎲 Découvertes', 'shuffle', state.categoryContent.random, 'random');
        html += createExpandableTile(config.cat4.title, config.cat4.icon, state.categoryContent.cat4, 'cat4');

        html += '</div>';
        html += '</div>';

        mainContent.innerHTML = html;

        // Attach click handlers
        attachCardClickHandlers();

    } catch (error) {
        console.error('Error loading category content:', error);
        mainContent.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">😕</div>
                <h3 class="empty-title">Erreur de chargement</h3>
                <p class="empty-text">Impossible de charger le contenu. Réessayez plus tard.</p>
                <button class="btn btn-primary" onclick="loadCategoryContent()">Réessayer</button>
            </div>
        `;
    }
}

/**
 * Create mini hero section
 */
function createMiniHero(media, catInfo) {
    const backdropUrl = media.backdrop_url || media.poster_url;
    const rating = media.rating ? media.rating.toFixed(1) : null;

    return `
        <div class="mini-hero mx-4">
            <div class="mini-hero-backdrop" style="background-image: url('${backdropUrl}')"></div>
            <div class="mini-hero-gradient"></div>
            <div class="mini-hero-content">
                <div class="mini-hero-info">
                    <span class="mini-hero-badge">
                        <i class="bi bi-${catInfo.icon}"></i>
                        ${catInfo.name} recommandé
                    </span>
                    <h2 class="mini-hero-title">${media.title}</h2>
                    <div class="mini-hero-meta">
                        <span>${media.year || ''}</span>
                        ${rating ? `<span class="mini-hero-rating">⭐ ${rating}</span>` : ''}
                    </div>
                    <div class="mini-hero-actions">
                        <button class="btn btn-primary" onclick="openMediaModal(${JSON.stringify(media).replace(/"/g, '&quot;')})">
                            <i class="bi bi-info-circle"></i> Détails
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

/**
 * Create expandable tile section
 */
function createExpandableTile(title, icon, items, id) {
    if (!items || items.length === 0) return '';

    const visibleItems = items.slice(0, 5);
    const hasMore = items.length > 5;

    // Store items for expansion
    if (!window.tileData) window.tileData = {};
    window.tileData[id] = items;

    return `
        <div class="expandable-tile" id="tile-${id}">
            <div class="tile-header">
                <h3 class="tile-title">
                    <i class="bi bi-${icon}"></i>
                    ${title}
                    <span class="tile-count">${items.length}</span>
                </h3>
                ${hasMore ? `
                    <button class="tile-toggle" onclick="toggleTile('${id}')">
                        Tout voir <i class="bi bi-chevron-right"></i>
                    </button>
                ` : ''}
            </div>
            <div class="tile-content">
                ${visibleItems.map(item => UI.createMediaCard(item)).join('')}
            </div>
        </div>
    `;
}

/**
 * Toggle expandable tile
 */
function toggleTile(id) {
    const tile = document.getElementById(`tile-${id}`);
    if (!tile) return;

    const isExpanded = tile.classList.toggle('expanded');
    const content = tile.querySelector('.tile-content');
    const items = window.tileData?.[id] || [];

    if (isExpanded) {
        // Show all items
        content.innerHTML = items.map(item => UI.createMediaCard(item)).join('');
    } else {
        // Show only first 5
        content.innerHTML = items.slice(0, 5).map(item => UI.createMediaCard(item)).join('');
    }

    // Re-attach click handlers
    attachCardClickHandlers();
}

// Keep loadTrendingContent for backwards compatibility
async function loadTrendingContent() {
    return loadCategoryContent('movie');
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
            // API returns direct array, not { results: [...] }
            state.searchResults = Array.isArray(results) ? results : (results?.results || []);

            if (mainContent) {
                mainContent.innerHTML = UI.createSearchResults(state.searchResults, type);
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
async function openMediaModal(media) {
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

    // Reset availability section
    const availabilitySection = document.getElementById('modalAvailability');
    const availabilityDetails = document.getElementById('availabilityDetails');
    const seasonSelector = document.getElementById('seasonSelector');
    const seasonGrid = document.getElementById('seasonGrid');

    availabilitySection.classList.add('d-none');
    seasonSelector.classList.add('d-none');

    // Fetch and display availability info if available
    if (media.already_available) {
        try {
            const availability = await api.getAvailability(media.media_type, media.id);
            if (availability && availability.available) {
                // Show availability section
                availabilitySection.classList.remove('d-none');

                // Build details HTML
                const details = [];

                if (availability.quality_info?.resolution) {
                    const codec = availability.quality_info?.video_codec || '';
                    details.push(`<span class="availability-detail"><i class="bi bi-display"></i> ${availability.quality_info.resolution} ${codec}</span>`);
                }

                if (availability.audio_languages?.length > 0) {
                    const langs = availability.audio_languages.map(formatLanguage).join(', ');
                    details.push(`<span class="availability-detail"><i class="bi bi-volume-up"></i> ${langs}</span>`);
                }

                if (availability.subtitle_languages?.length > 0) {
                    const subs = availability.subtitle_languages.map(formatLanguage).join(', ');
                    details.push(`<span class="availability-detail"><i class="bi bi-chat-quote"></i> ${subs}</span>`);
                }

                if (availability.file_size_gb) {
                    details.push(`<span class="availability-detail"><i class="bi bi-hdd"></i> ${availability.file_size_gb} GB</span>`);
                }

                // For series: show available seasons
                if (availability.seasons_available?.length > 0) {
                    const seasonsText = availability.seasons_available.length > 5
                        ? `Saisons 1-${availability.seasons_available.length}`
                        : `Saisons ${availability.seasons_available.join(', ')}`;
                    details.push(`<span class="availability-detail"><i class="bi bi-collection"></i> ${seasonsText}</span>`);
                }

                availabilityDetails.innerHTML = details.join('');
            }
        } catch (e) {
            console.log('Could not fetch availability details:', e);
        }
    }

    // Handle series: show season selector
    const isSeries = media.media_type === 'tv' || media.media_type === 'series' || media.media_type === 'anime';
    if (isSeries && !media.already_available) {
        try {
            // For now, generate a simple season selector
            // In the future, we can fetch seasons from TMDB and compare with available
            const seasonsAvailability = await api.getSeasonsAvailability(media.id).catch(() => null);
            const availableSeasons = seasonsAvailability?.seasons || [];

            // Get total seasons (we'd need to fetch this from TMDB, for now use a default)
            const totalSeasons = media.seasons_count || 1;

            if (totalSeasons > 0) {
                seasonSelector.classList.remove('d-none');

                let seasonsHtml = '';
                for (let i = 1; i <= Math.min(totalSeasons, 10); i++) {
                    const isAvailable = availableSeasons.includes(i);
                    seasonsHtml += `
                        <label class="season-checkbox ${isAvailable ? 'available' : ''}" title="${isAvailable ? 'Déjà disponible' : 'Non disponible'}">
                            <input type="checkbox" name="seasons" value="${i}" 
                                   ${isAvailable ? 'disabled' : ''}>
                            <span class="season-number">S${i}</span>
                            ${isAvailable ? '<i class="bi bi-check-circle-fill season-check"></i>' : ''}
                        </label>
                    `;
                }

                // Add "All seasons" option if not all available
                if (availableSeasons.length < totalSeasons) {
                    seasonsHtml = `
                        <label class="season-checkbox season-all">
                            <input type="checkbox" name="seasons" value="all" id="selectAllSeasons">
                            <span class="season-number">Toutes</span>
                        </label>
                    ` + seasonsHtml;
                }

                seasonGrid.innerHTML = seasonsHtml;

                // Add event listener for "select all"
                const selectAll = document.getElementById('selectAllSeasons');
                if (selectAll) {
                    selectAll.addEventListener('change', (e) => {
                        const checkboxes = seasonGrid.querySelectorAll('input[name="seasons"]:not([value="all"]):not(:disabled)');
                        checkboxes.forEach(cb => cb.checked = e.target.checked);
                    });
                }
            }
        } catch (e) {
            console.log('Could not fetch seasons:', e);
        }
    }

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
 * Format language code to readable name
 */
function formatLanguage(code) {
    const langMap = {
        'fra': '🇫🇷 Français',
        'fre': '🇫🇷 Français',
        'french': '🇫🇷 Français',
        'eng': '🇬🇧 English',
        'english': '🇬🇧 English',
        'jpn': '🇯🇵 日本語',
        'japanese': '🇯🇵 日本語',
        'ger': '🇩🇪 Deutsch',
        'german': '🇩🇪 Deutsch',
        'spa': '🇪🇸 Español',
        'spanish': '🇪🇸 Español',
        'ita': '🇮🇹 Italiano',
        'italian': '🇮🇹 Italiano',
        'por': '🇵🇹 Português',
        'kor': '🇰🇷 한국어',
        'chi': '🇨🇳 中文',
        'und': 'Unknown'
    };
    return langMap[code?.toLowerCase()] || code?.toUpperCase() || 'Unknown';
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
            external_id: String(state.selectedMedia.id),
            media_type: state.selectedMedia.media_type,
            title: state.selectedMedia.title,
            year: state.selectedMedia.year,
            poster_url: state.selectedMedia.poster_url,
            overview: state.selectedMedia.overview || null,
            quality_preference: '1080p',
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
        const errorMessage = error.message || 'Erreur lors de la demande';
        UI.showToast(errorMessage, 'danger');
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

            // Check search results first
            media = state.searchResults.find(m =>
                String(m.id) === mediaId && (m.source || 'tmdb') === source
            );

            // Check category content (hero + all sections)
            if (!media) {
                const allCategoryItems = [
                    state.categoryContent.hero,
                    ...state.categoryContent.top_rated,
                    ...state.categoryContent.classics,
                    ...state.categoryContent.hidden_gems,
                    ...state.categoryContent.random,
                    ...state.categoryContent.cat1,
                    ...state.categoryContent.cat2,
                    ...state.categoryContent.cat3,
                    ...state.categoryContent.cat4
                ].filter(Boolean);

                media = allCategoryItems.find(m => String(m.id) === mediaId);
            }

            // Check trending (fallback)
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
            const query = e.target.value;
            if (query.length >= 2) {
                performSearch(query, state.currentCategory);
            } else if (query.length === 0) {
                // Return to category view
                loadCategoryContent();
            }
        });

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchInput.value = '';
                loadCategoryContent();
            }
        });
    }

    // Category pills (homepage navigation between Films/Séries/Animés)
    document.querySelectorAll('.category-pill').forEach(pill => {
        pill.addEventListener('click', (e) => {
            const category = e.currentTarget.dataset.category;

            // Clear search when switching categories
            if (searchInput) searchInput.value = '';
            state.searchQuery = '';

            // Load new category content
            loadCategoryContent(category);
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

/**
 * Open gallery modal with all items from a row
 */
function openGalleryModal(rowId) {
    const data = window.rowData?.[rowId];
    if (!data) return;

    const modal = document.getElementById('galleryModal');
    if (!modal) return;

    // Update modal title and count
    document.getElementById('galleryTitle').textContent = data.title;
    document.getElementById('galleryCount').textContent = `${data.items.length} résultats`;

    // Update title icon based on type
    const titleIcon = modal.querySelector('.gallery-title i');
    if (titleIcon) {
        const iconMap = {
            'movie': 'bi-film',
            'tv': 'bi-tv',
            'anime': 'bi-stars'
        };
        titleIcon.className = `bi ${iconMap[data.type] || 'bi-film'}`;
    }

    // Populate grid with cards
    const grid = document.getElementById('galleryGrid');
    grid.innerHTML = data.items.map(item => UI.createMediaCard(item)).join('');

    // Attach click handlers to new cards
    grid.querySelectorAll('.media-card').forEach(card => {
        card.addEventListener('click', () => {
            const mediaId = card.dataset.mediaId;
            const source = card.dataset.mediaSource;

            // Find media in row data
            const media = data.items.find(m =>
                String(m.id) === mediaId && (m.source || 'tmdb') === source
            );

            if (media) {
                // Close gallery modal first
                const galleryInstance = bootstrap.Modal.getInstance(modal);
                if (galleryInstance) galleryInstance.hide();

                // Small delay before opening detail modal
                setTimeout(() => openMediaModal(media), 300);
            }
        });
    });

    // Show modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

/**
 * Setup touch scrolling for media rows (mobile)
 */
function setupTouchScrolling() {
    document.querySelectorAll('.media-row').forEach(row => {
        let isDown = false;
        let startX;
        let scrollLeft;

        row.addEventListener('mousedown', (e) => {
            isDown = true;
            row.classList.add('active');
            startX = e.pageX - row.offsetLeft;
            scrollLeft = row.scrollLeft;
        });

        row.addEventListener('mouseleave', () => {
            isDown = false;
            row.classList.remove('active');
        });

        row.addEventListener('mouseup', () => {
            isDown = false;
            row.classList.remove('active');
        });

        row.addEventListener('mousemove', (e) => {
            if (!isDown) return;
            e.preventDefault();
            const x = e.pageX - row.offsetLeft;
            const walk = (x - startX) * 2;
            row.scrollLeft = scrollLeft - walk;
        });

        // Touch events for mobile
        row.addEventListener('touchstart', (e) => {
            startX = e.touches[0].pageX - row.offsetLeft;
            scrollLeft = row.scrollLeft;
        }, { passive: true });

        row.addEventListener('touchmove', (e) => {
            const x = e.touches[0].pageX - row.offsetLeft;
            const walk = (x - startX) * 2;
            row.scrollLeft = scrollLeft - walk;
        }, { passive: true });
    });

    // Update scroll indicators
    updateScrollIndicators();
}

/**
 * Update scroll indicators for mobile
 */
function updateScrollIndicators() {
    document.querySelectorAll('.media-section').forEach(section => {
        const row = section.querySelector('.media-row');
        const indicatorsContainer = section.querySelector('.scroll-indicators');

        if (!row || !indicatorsContainer) return;

        // Calculate number of pages
        const cardWidth = 160; // Average card width
        const visibleCards = Math.floor(row.clientWidth / cardWidth);
        const totalCards = row.querySelectorAll('.media-card').length;
        const pages = Math.ceil(totalCards / visibleCards);

        // Don't show indicators if only one page
        if (pages <= 1) {
            indicatorsContainer.innerHTML = '';
            return;
        }

        // Create dots
        indicatorsContainer.innerHTML = Array(Math.min(pages, 5))
            .fill(0)
            .map((_, i) => `<div class="scroll-dot ${i === 0 ? 'active' : ''}"></div>`)
            .join('');

        // Update active dot on scroll
        let scrollTimeout;
        row.addEventListener('scroll', () => {
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(() => {
                const scrollPercent = row.scrollLeft / (row.scrollWidth - row.clientWidth);
                const activeDot = Math.min(
                    Math.floor(scrollPercent * pages),
                    pages - 1
                );
                indicatorsContainer.querySelectorAll('.scroll-dot').forEach((dot, i) => {
                    dot.classList.toggle('active', i === activeDot);
                });
            }, 50);
        });

        // Click on dot to scroll
        indicatorsContainer.querySelectorAll('.scroll-dot').forEach((dot, i) => {
            dot.addEventListener('click', () => {
                const targetScroll = (row.scrollWidth - row.clientWidth) * (i / (pages - 1));
                row.scrollTo({ left: targetScroll, behavior: 'smooth' });
            });
        });
    });
}

/**
 * Create media card with type badge for search results
 */
function createMediaCardWithTypeBadge(media) {
    const card = UI.createMediaCard(media);
    // Add type badge to the card
    const typeClass = media.media_type || 'movie';
    const typeBadge = `<span class="media-type-badge ${typeClass}">${UI.getMediaTypeLabel(media.media_type)}</span>`;

    // Insert badge after poster opening tag
    return card.replace('<div class="media-poster">', `<div class="media-poster">${typeBadge}`);
}

/**
 * Expand a search section to show all results in gallery modal
 */
function expandSearchSection(type) {
    const data = window.searchSections?.[type];
    if (!data) return;

    // Create temporary row data for gallery modal
    if (!window.rowData) window.rowData = {};
    const tempId = `search-${type}`;
    window.rowData[tempId] = {
        title: data.title,
        icon: data.icon,
        items: data.items,
        type: type
    };

    // Open gallery modal with this data
    openGalleryModal(tempId);
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', initApp);

// Export for global access
window.scrollRow = scrollRow;
window.openMediaModal = openMediaModal;
window.requestMedia = requestMedia;
window.logout = logout;
window.openGalleryModal = openGalleryModal;
window.expandSearchSection = expandSearchSection;
window.toggleTile = toggleTile;
window.loadCategoryContent = loadCategoryContent;

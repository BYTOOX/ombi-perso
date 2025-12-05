/**
 * Plex Kiosk - Authentication Module
 * Handles login, registration, and session management
 */

// API Configuration
const API_BASE = '/api/v1';

// DOM Elements
const loginForm = document.getElementById('loginForm');
const loginBtn = document.getElementById('loginBtn');
const loginError = document.getElementById('loginError');
const loginErrorMessage = document.getElementById('loginErrorMessage');
const plexLoginBtn = document.getElementById('plexLoginBtn');
const registerLink = document.getElementById('registerLink');
const registerForm = document.getElementById('registerForm');
const registerModal = document.getElementById('registerModal') ?
    new bootstrap.Modal(document.getElementById('registerModal')) : null;

// Password Toggle
document.querySelectorAll('.toggle-password').forEach(btn => {
    btn.addEventListener('click', function () {
        const input = this.parentElement.querySelector('input');
        const icon = this.querySelector('i');

        if (input.type === 'password') {
            input.type = 'text';
            icon.classList.replace('bi-eye', 'bi-eye-slash');
        } else {
            input.type = 'password';
            icon.classList.replace('bi-eye-slash', 'bi-eye');
        }
    });
});

// Check if already logged in
document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('access_token');
    if (token) {
        // Verify token is still valid
        verifyToken(token).then(valid => {
            if (valid) {
                window.location.href = '/';
            }
        });
    }
});

/**
 * Verify if token is still valid
 */
async function verifyToken(token) {
    try {
        const response = await fetch(`${API_BASE}/auth/me`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        return response.ok;
    } catch {
        return false;
    }
}

/**
 * Show loading state on button
 */
function setLoading(button, loading) {
    const btnText = button.querySelector('.btn-text');
    const btnLoader = button.querySelector('.btn-loader');

    if (loading) {
        btnText.classList.add('d-none');
        btnLoader.classList.remove('d-none');
        button.disabled = true;
    } else {
        btnText.classList.remove('d-none');
        btnLoader.classList.add('d-none');
        button.disabled = false;
    }
}

/**
 * Show error message
 */
function showError(element, messageEl, message) {
    messageEl.textContent = message;
    element.classList.remove('d-none');

    // Auto-hide after 5 seconds
    setTimeout(() => {
        element.classList.add('d-none');
    }, 5000);
}

/**
 * Handle Login Form Submit
 */
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;

        if (!username || !password) {
            showError(loginError, loginErrorMessage, 'Veuillez remplir tous les champs');
            return;
        }

        setLoading(loginBtn, true);
        loginError.classList.add('d-none');

        try {
            // Create form data for OAuth2 password flow
            const formData = new URLSearchParams();
            formData.append('username', username);
            formData.append('password', password);

            const response = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                // Store token
                localStorage.setItem('access_token', data.access_token);
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }

                // Store user info
                if (data.user) {
                    localStorage.setItem('user', JSON.stringify(data.user));
                }

                // Redirect to main app
                window.location.href = '/';
            } else {
                showError(loginError, loginErrorMessage,
                    data.detail || 'Identifiants incorrects');
            }
        } catch (err) {
            console.error('Login error:', err);
            showError(loginError, loginErrorMessage,
                'Erreur de connexion au serveur');
        } finally {
            setLoading(loginBtn, false);
        }
    });
}

/**
 * Handle Plex OAuth Login
 */
if (plexLoginBtn) {
    plexLoginBtn.addEventListener('click', async () => {
        try {
            // Get Plex auth URL from backend
            const response = await fetch(`${API_BASE}/auth/plex/url`);
            const data = await response.json();

            if (data.auth_url) {
                // Redirect to Plex for authentication
                window.location.href = data.auth_url;
            } else {
                showError(loginError, loginErrorMessage,
                    'Impossible de se connecter à Plex');
            }
        } catch (err) {
            console.error('Plex auth error:', err);
            showError(loginError, loginErrorMessage,
                'Erreur lors de la connexion Plex');
        }
    });
}

/**
 * Handle Register Link
 */
if (registerLink && registerModal) {
    registerLink.addEventListener('click', (e) => {
        e.preventDefault();
        registerModal.show();
    });
}

/**
 * Handle Register Form Submit
 */
if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const username = document.getElementById('regUsername').value.trim();
        const email = document.getElementById('regEmail').value.trim();
        const password = document.getElementById('regPassword').value;
        const passwordConfirm = document.getElementById('regPasswordConfirm').value;
        const registerError = document.getElementById('registerError');
        const submitBtn = registerForm.querySelector('button[type="submit"]');

        // Validation
        if (password !== passwordConfirm) {
            registerError.textContent = 'Les mots de passe ne correspondent pas';
            registerError.classList.remove('d-none');
            return;
        }

        if (password.length < 6) {
            registerError.textContent = 'Le mot de passe doit contenir au moins 6 caractères';
            registerError.classList.remove('d-none');
            return;
        }

        setLoading(submitBtn, true);
        registerError.classList.add('d-none');

        try {
            const response = await fetch(`${API_BASE}/auth/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username,
                    email,
                    password
                })
            });

            const data = await response.json();

            if (response.ok) {
                // Auto-login after registration
                localStorage.setItem('access_token', data.access_token);
                if (data.user) {
                    localStorage.setItem('user', JSON.stringify(data.user));
                }

                registerModal.hide();
                window.location.href = '/';
            } else {
                registerError.textContent = data.detail || 'Erreur lors de l\'inscription';
                registerError.classList.remove('d-none');
            }
        } catch (err) {
            console.error('Register error:', err);
            registerError.textContent = 'Erreur de connexion au serveur';
            registerError.classList.remove('d-none');
        } finally {
            setLoading(submitBtn, false);
        }
    });
}

/**
 * Handle Plex OAuth Callback
 * Check URL for Plex callback parameters
 */
(function handlePlexCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const plexToken = urlParams.get('plex_token');

    if (plexToken) {
        // Exchange Plex token for our JWT
        fetch(`${API_BASE}/auth/plex/callback`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ plex_token: plexToken })
        })
            .then(response => response.json())
            .then(data => {
                if (data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                    if (data.user) {
                        localStorage.setItem('user', JSON.stringify(data.user));
                    }
                    // Clear URL params and redirect
                    window.history.replaceState({}, document.title, '/');
                    window.location.href = '/';
                }
            })
            .catch(err => {
                console.error('Plex callback error:', err);
            });
    }
})();

# PHASE 0 - JOUR 8: Sécuriser CORS

**Date**: 2026-01-18
**Statut**: ✅ Complété

## Objectif

Remplacer la configuration CORS `allow_origins=["*"]` dangereuse par une configuration sécurisée basée sur l'environnement.

---

## Problème Identifié

### Configuration actuelle (AVANT):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ❌ TRÈS DANGEREUX
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Risques:

1. **Cross-Site Request Forgery (CSRF)**: Toute origine peut faire des requêtes authentifiées
2. **Vol de données**: Sites malveillants peuvent récupérer données utilisateur
3. **Attaques XSS**: Scripts malicieux peuvent accéder à l'API
4. **Non-conformité sécurité**: Fail audits de sécurité

---

## Solution Implémentée

### Configuration dynamique (APRÈS):

```python
# Development mode
if settings.debug:
    allowed_origins = [
        "http://localhost:8765",
        "http://localhost:5173",  # Vite
        "http://localhost:3000",
        "http://127.0.0.1:8765",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

# Production mode
else:
    allowed_origins = []

    if settings.frontend_url:
        allowed_origins.append(settings.frontend_url)

    if settings.cors_origins:
        for origin in settings.cors_origins.split(","):
            allowed_origins.append(origin.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # ✅ SÉCURISÉ
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "Accept-Language",
        "Content-Language",
    ],
    expose_headers=["Content-Range", "X-Content-Range"],
    max_age=3600,
)
```

---

## Changements Effectués

### 1. Configuration Settings

**Fichier**: [backend/app/config.py](backend/app/config.py)

**Ajouts**:
```python
# CORS (Security)
frontend_url: Optional[str] = Field(
    default=None,
    description="Frontend URL for production CORS (e.g., https://plex-kiosk.yourdomain.com)"
)
cors_origins: Optional[str] = Field(
    default=None,
    description="Comma-separated additional CORS origins"
)
```

### 2. Main Application

**Fichier**: [backend/app/main.py](backend/app/main.py)

**Changements**:

**a) Build Origins List**:
```python
allowed_origins = []

if settings.debug:
    # Development: localhost only
    allowed_origins = [
        "http://localhost:8765",
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:8765",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
else:
    # Production: configured domains only
    if settings.frontend_url:
        allowed_origins.append(settings.frontend_url)

    if settings.cors_origins:
        additional_origins = [
            origin.strip()
            for origin in settings.cors_origins.split(",")
            if origin.strip()
        ]
        allowed_origins.extend(additional_origins)
```

**b) Logging**:
```python
logger.info(f"CORS allowed origins: {allowed_origins}")

if not allowed_origins and not settings.debug:
    logger.warning(
        "CORS: Production mode but no origins configured! "
        "Set FRONTEND_URL or CORS_ORIGINS in environment."
    )
```

**c) Secure Middleware**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "Accept-Language",
        "Content-Language",
    ],
    expose_headers=["Content-Range", "X-Content-Range"],
    max_age=3600,
)
```

### 3. Environment Variables

**Fichier**: [.env.example](.env.example)

**Ajouts**:
```bash
# ====================================
# CORS (Security - Production Only)
# ====================================
# In development (DEBUG=true), localhost origins are automatically allowed
# In production (DEBUG=false), you MUST configure these:

# Frontend URL for CORS
# FRONTEND_URL=https://plex-kiosk.yourdomain.com

# Additional CORS origins (comma-separated)
# CORS_ORIGINS=https://app.yourdomain.com,https://admin.yourdomain.com
```

---

## Configuration par Environnement

### Development (DEBUG=true)

**Pas de configuration nécessaire** - Localhost autorisé automatiquement.

**.env**:
```bash
DEBUG=true
```

**Origins autorisées**:
- `http://localhost:8765`
- `http://localhost:5173` (Vite dev server)
- `http://localhost:3000`
- `http://127.0.0.1:8765`
- `http://127.0.0.1:5173`
- `http://127.0.0.1:3000`

### Production (DEBUG=false)

**Configuration OBLIGATOIRE**.

**.env**:
```bash
DEBUG=false
FRONTEND_URL=https://plex-kiosk.yourdomain.com
```

**Origins autorisées**:
- `https://plex-kiosk.yourdomain.com`

### Production Multi-Domaines

**.env**:
```bash
DEBUG=false
FRONTEND_URL=https://plex-kiosk.yourdomain.com
CORS_ORIGINS=https://app.yourdomain.com,https://admin.yourdomain.com
```

**Origins autorisées**:
- `https://plex-kiosk.yourdomain.com`
- `https://app.yourdomain.com`
- `https://admin.yourdomain.com`

---

## Sécurité Renforcée

### Limitations Implémentées

| Paramètre | Avant | Après |
|-----------|-------|-------|
| **Origins** | `["*"]` ❌ | Liste blanche ✅ |
| **Methods** | `["*"]` ❌ | Liste explicite ✅ |
| **Headers** | `["*"]` ❌ | Liste explicite ✅ |
| **Credentials** | `True` ⚠️ | `True` avec origins ✅ |
| **Max Age** | Non défini | 3600s (1h) ✅ |

### Méthodes Autorisées

Seules les méthodes nécessaires:
- `GET` - Récupération données
- `POST` - Création ressources
- `PUT` - Mise à jour complète
- `DELETE` - Suppression
- `PATCH` - Mise à jour partielle
- `OPTIONS` - Preflight requests

**Bloqué**: `TRACE`, `CONNECT`, autres méthodes dangereuses.

### Headers Autorisés

Seuls headers nécessaires:
- `Content-Type` - Type de contenu
- `Authorization` - Tokens JWT
- `Accept` - Format de réponse
- `Accept-Language` - Langue
- `Content-Language` - Langue du contenu

**Bloqué**: Headers arbitraires.

### Exposed Headers

Headers exposés au client:
- `Content-Range` - Pagination
- `X-Content-Range` - Pagination custom

---

## Vérification

### Test Development Mode

```bash
# Start avec DEBUG=true
DEBUG=true uvicorn app.main:app --reload

# Tester depuis localhost:5173 (Vite)
curl -H "Origin: http://localhost:5173" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS \
     http://localhost:8765/api/v1/auth/login

# Devrait répondre avec:
# Access-Control-Allow-Origin: http://localhost:5173
```

### Test Production Mode

```bash
# Start avec DEBUG=false
DEBUG=false \
FRONTEND_URL=https://plex-kiosk.example.com \
uvicorn app.main:app

# Tester origine autorisée
curl -H "Origin: https://plex-kiosk.example.com" \
     -X OPTIONS \
     http://localhost:8765/api/health

# Devrait répondre: Access-Control-Allow-Origin: https://plex-kiosk.example.com

# Tester origine NON autorisée
curl -H "Origin: https://malicious-site.com" \
     -X OPTIONS \
     http://localhost:8765/api/health

# Devrait répondre: PAS de header Access-Control-Allow-Origin
```

### Logs Verification

```bash
# Start app
docker-compose up -d

# Check logs
docker-compose logs plex-kiosk | grep CORS

# Should see:
# INFO: CORS allowed origins: ['http://localhost:8765', 'http://localhost:5173', ...]
# OR (production):
# INFO: CORS allowed origins: ['https://plex-kiosk.yourdomain.com']
```

---

## Troubleshooting

### Erreur: "Origin not allowed"

**Symptôme**: Frontend ne peut pas accéder API.

**Browser console**:
```
Access to fetch at 'http://localhost:8765/api/...' from origin 'http://localhost:5173'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present.
```

**Solution**:

1. **Development**: Vérifier `DEBUG=true` dans .env
2. **Production**: Ajouter origine dans `FRONTEND_URL` ou `CORS_ORIGINS`

```bash
# .env
FRONTEND_URL=https://your-frontend-url.com
```

3. Restart backend:
```bash
docker-compose restart plex-kiosk
```

### Warning: "Production mode but no origins configured"

**Symptôme**: Log warning au démarrage.

**Solution**: Configurer `FRONTEND_URL` en production.

```bash
# .env
DEBUG=false
FRONTEND_URL=https://plex-kiosk.yourdomain.com
```

### Credentials Not Working

**Symptôme**: Cookies/auth pas envoyés.

**Cause**: Origin pas dans whitelist avec `allow_credentials=True`.

**Solution**: Vérifier origine exacte (protocol + domain + port).

```javascript
// Frontend - doit matcher EXACTEMENT
const API_URL = 'https://plex-kiosk.yourdomain.com'; // ✅
// PAS:
const API_URL = 'https://plex-kiosk.yourdomain.com/'; // ❌ (trailing slash)
```

---

## Best Practices

### Development

```bash
# .env.local
DEBUG=true
# Pas besoin de configurer CORS
```

### Staging

```bash
# .env.staging
DEBUG=false
FRONTEND_URL=https://staging.plex-kiosk.yourdomain.com
```

### Production

```bash
# .env.production
DEBUG=false
FRONTEND_URL=https://plex-kiosk.yourdomain.com
# Si CDN:
CORS_ORIGINS=https://cdn.yourdomain.com
```

### Docker Compose

```yaml
plex-kiosk:
  environment:
    - DEBUG=false
    - FRONTEND_URL=${FRONTEND_URL:?Frontend URL required in production}
    - CORS_ORIGINS=${CORS_ORIGINS:-}
```

---

## Sécurité Additionnelle

### HTTPS Only (Production)

En production, TOUJOURS utiliser HTTPS:

```bash
# ✅ Correct
FRONTEND_URL=https://plex-kiosk.yourdomain.com

# ❌ Dangereux en production
FRONTEND_URL=http://plex-kiosk.yourdomain.com
```

### CSP Headers (Optionnel)

Pour sécurité additionnelle, ajouter Content Security Policy:

```python
# main.py
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["plex-kiosk.yourdomain.com", "*.yourdomain.com"]
)
```

### Rate Limiting

Limiter requêtes par IP pour prévenir abus:

```python
# TODO: Ajouter rate limiting middleware
# pip install slowapi
```

---

## Conformité

### OWASP Top 10

- ✅ **A1 - Broken Access Control**: Origins whitelist
- ✅ **A5 - Security Misconfiguration**: Pas de wildcard
- ✅ **A7 - XSS**: Headers contrôlés

### GDPR

- ✅ Contrôle accès données personnelles
- ✅ Logs des origins autorisées

---

## Prochaines Étapes

- ✅ JOUR 8 terminé
- ⏭️ **JOUR 9-10**: Setup Vue.js 3 + Vite + Pinia + TypeScript
  - Initialiser projet Vue 3
  - Configurer Vite
  - Setup Pinia stores
  - API client avec CORS

---

## Fichiers Modifiés (Résumé)

```
backend/
  app/
    config.py          # + frontend_url, cors_origins
    main.py            # CORS configuration sécurisée

.env.example           # + CORS section

docs/
  PHASE0_JOUR8_CORS.md # Ce fichier
```

---

**Auteur**: Claude Code
**Phase**: Phase 0 - Assainissement
**Statut**: ✅ Complété

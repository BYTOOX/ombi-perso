# Plex Kiosk 🎬

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://docker.com)

Système de kiosque self-service pour demander des films, séries et animés avec intégration automatique Plex.

![Screenshot](docs/screenshot.png)

## ✨ Fonctionnalités

- 🔍 **Recherche unifiée** - TMDB (films/séries) + AniList (animés)
- 🤖 **IA Locale** - Scoring intelligent des torrents via Ollama/Qwen
- ⬇️ **Téléchargement automatique** - YGGtorrent + qBittorrent
- 📺 **Intégration Plex** - Scan auto, renommage Filebot, routing librairies
- 🔔 **Notifications** - Discord + Plex
- 👥 **Multi-utilisateurs** - JWT + SSO Plex, limites quotidiennes

## 🚀 Démarrage rapide

```bash
# Cloner
git clone https://github.com/votre-repo/ombi-perso.git
cd ombi-perso

# Configurer
cp .env.example .env
nano .env  # Remplir les credentials

# Lancer
docker compose up -d

# Accéder
open http://localhost:8765
```

## 📋 Prérequis

- Docker & Docker Compose
- Compte YGGtorrent
- Clé API TMDB
- qBittorrent avec WebUI
- Plex Media Server
- Ollama avec modèle Qwen (optionnel mais recommandé)

## ⚙️ Configuration

Voir [DEPLOYMENT.md](docs/DEPLOYMENT.md) pour le guide complet.

### Variables essentielles

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Clé JWT (générer avec `openssl rand -hex 32`) |
| `TMDB_API_KEY` | Clé API TMDB |
| `YGG_USERNAME` | Username YGGtorrent |
| `YGG_PASSWORD` | Password YGGtorrent |
| `PLEX_URL` | URL du serveur Plex |
| `PLEX_TOKEN` | Token d'authentification Plex |
| `QBITTORRENT_URL` | URL du WebUI qBittorrent |
| `DISCORD_WEBHOOK_URL` | Webhook Discord pour notifications |

### Configuration des librairies

```env
LIBRARY_PATHS={"movie": "/media/Films", "series": "/media/Séries", "anime": "/media/Animés"}
```

## 🏗️ Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   FastAPI   │────▶│   Services  │
│  Alpine.js  │     │    REST     │     │   Layer     │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼              ▼           ▼           ▼              ▼
              ┌──────────┐  ┌──────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐
              │  TMDB    │  │ AniList  │  │  YGG    │  │ Ollama  │  │   Plex   │
              └──────────┘  └──────────┘  └─────────┘  └─────────┘  └──────────┘
```

## 📁 Structure du projet

```
ombi-perso/
├── backend/
│   ├── app/
│   │   ├── api/v1/         # Endpoints REST
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # Business logic
│   │   ├── config.py       # Configuration
│   │   └── main.py         # FastAPI app
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── index.html          # SPA Alpine.js
│   └── static/
│       ├── css/styles.css
│       └── js/
├── docs/
│   ├── DEPLOYMENT.md
│   └── ANILIST_SETUP.md
├── docker-compose.yml
└── .env.example
```

## 🔧 Développement

```bash
# Backend seul
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Avec Docker (mode dev)
docker compose -f docker-compose.dev.yml up
```

## 📝 API Documentation

Disponible en mode debug : `http://localhost:8765/api/docs`

### Endpoints principaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/v1/auth/login` | Connexion |
| POST | `/api/v1/auth/plex` | SSO Plex |
| GET | `/api/v1/search` | Recherche unifiée |
| POST | `/api/v1/requests` | Nouvelle demande |
| GET | `/api/v1/requests` | Liste des demandes |
| GET | `/api/v1/admin/stats` | Statistiques (admin) |

## 🤝 Contribution

Les contributions sont les bienvenues ! Voir [CONTRIBUTING.md](CONTRIBUTING.md).

## 📄 Licence

MIT License - Voir [LICENSE](LICENSE)

---

Fait avec ❤️ pour la communauté Plex

# 🎬 PLEX KIOSK V2 - Product Requirements Document

## Système Intelligent de Gestion de Médiathèque

**Version:** 2.0  
**Date:** Janvier 2026  
**Nom de code:** "AI Media Manager"  
**Modèle IA:** Qwen3-VL-30B-A3B via Ollama

---

# 📑 TABLE DES MATIÈRES

1. [Executive Summary](#1-executive-summary)
2. [Analyse V1 & Problèmes](#2-analyse-v1--problèmes)
3. [Vision Produit V2](#3-vision-produit-v2)
4. [Features Principales](#4-features-principales)
5. [Architecture V2](#5-architecture-v2)
6. [Intégrations IA](#6-intégrations-ia)
7. [Modèles de Données](#7-modèles-de-données)
8. [API Endpoints V2](#8-api-endpoints-v2)
9. [Roadmap & Phases](#9-roadmap--phases)
10. [Pré-prompts Claude Code](#10-pré-prompts-claude-code)

---

# 1. EXECUTIVE SUMMARY

## 1.1 Objectif

Transformer Plex Kiosk d'une application de demandes manuelle en un **système autonome intelligent** de gestion de médiathèque, inspiré de Sonarr/Radarr mais avec l'IA au cœur.

## 1.2 Problèmes résolus

| Problème actuel | Solution V2 |
|-----------------|-------------|
| Téléchargement manuel uniquement | Suivi automatique des séries + téléchargement à la sortie |
| Pas d'upgrade de qualité | Surveillance VOSTFR→MULTI, SD→HD→4K automatique |
| Aucune analyse de bibliothèque | Agent IA analysant qualité, codecs, manques |
| Frontend monolithique | Architecture moderne Vue.js 3 |
| Backend fragile (async/sync mixé) | Full async + Celery pour background tasks |

## 1.3 KPIs de succès

- 90% des séries suivies téléchargées automatiquement dans les 24h
- Réduction de 80% des interventions manuelles admin
- 100% des upgrades VOSTFR→MULTI détectés et proposés
- Temps de réponse UI < 200ms

---

# 2. ANALYSE V1 & PROBLÈMES

## 2.1 Fonctionnalités V1 existantes ✅

- **Auth**: JWT + Plex SSO, rôles Admin/User, limites quotidiennes
- **Recherche**: TMDB (films/séries) + AniList (animés), Discovery pages
- **Demandes**: Workflow PENDING→COMPLETED, sélection qualité/saisons
- **Pipeline**: YggAPI + FlareSolverr, scoring IA torrents, qBittorrent
- **Post-download**: Renommage Plex, templates configurables
- **Admin**: Dashboard stats, gestion users, config paths, logs

## 2.2 Problèmes critiques à corriger 🔴

### Architecture Frontend
```
PROBLÈME:
├── admin.html      → 2943 lignes, tout inline !
├── static/js/app.js → 1530 lignes, état global dispersé
```
**Solution:** Migration Vue.js 3 + Vite + Pinia

### Architecture Backend
```python
# PROBLÈME: Mélange async/sync dangereux
def _resolve_title(self, ...):
    resolved = asyncio.get_event_loop().run_until_complete(...)  # ⚠️
```
**Solution:** Full async + Celery workers

### Autres problèmes
- SQLite en prod → PostgreSQL
- CORS ouvert `allow_origins=["*"]` → Configuration stricte
- Pas de migrations → Alembic
- Singletons mal gérés → Dependency Injection

---

# 3. VISION PRODUIT V2

## 3.1 Positionnement

> **Plex Kiosk V2** = Sonarr + Radarr + IA Intelligente

Un système qui :
1. **Anticipe** les besoins (suivi séries, nouveautés)
2. **Surveille** la qualité (upgrades automatiques)
3. **Analyse** la bibliothèque (recommandations IA)
4. **Agit** de manière autonome (mais supervisée)

## 3.2 Principes directeurs

| Principe | Description |
|----------|-------------|
| **IA-First** | L'IA au cœur de chaque décision |
| **Autonomie contrôlée** | Actions automatiques mais traçables |
| **Qualité progressive** | Amélioration continue sans intervention |
| **Transparence totale** | Chaque décision IA expliquée et loguée |

---

# 4. FEATURES PRINCIPALES

## 4.1 🔄 Feature 1: Suivi Automatique des Séries

### Description
Système type Sonarr permettant de "suivre" une série et télécharger automatiquement chaque nouvel épisode.

### User Stories
```gherkin
Scenario: Téléchargement automatique nouvel épisode
  Given "One Piece" est dans mes séries suivies
  And un nouvel épisode sort le dimanche
  When le système détecte la disponibilité d'un torrent
  Then il sélectionne le meilleur torrent via IA
  And lance le téléchargement automatiquement
  And je reçois une notification
```

### Règles métier
1. **Sources calendrier:** TMDB + AniList + TVMaze
2. **Fenêtre recherche:** air_date + 2h, puis toutes les 2h pendant 48h
3. **Sélection torrent:** Score IA ≥ 70, seeders ≥ 5

### Modèle de données
```python
class SeriesFollow(Base):
    id: int
    user_id: int
    tmdb_id: Optional[int]
    anilist_id: Optional[int]
    title: str
    quality_preference: str = "1080p"  # 720p, 1080p, 4K
    language_preference: str = "MULTI"  # VOSTFR, MULTI, VF
    auto_download: bool = True
    status: str = "active"  # active, paused, completed
    next_episode_air_date: Optional[datetime]

class EpisodeRelease(Base):
    id: int
    series_follow_id: int
    season: int
    episode: int
    air_date: datetime
    status: str  # pending, searching, downloading, completed, failed
    search_attempts: int = 0
```

---

## 4.2 ⬆️ Feature 2: Surveillance & Upgrade Automatique

### Description
Surveiller les médias existants pour détecter et appliquer des upgrades (VOSTFR→MULTI, 1080p→4K, x264→HEVC).

### User Stories
```gherkin
Scenario: Détection upgrade VOSTFR → MULTI
  Given j'ai "Dune 2" en VOSTFR dans ma bibliothèque
  When une version MULTI devient disponible sur YGG
  Then le système détecte l'upgrade possible
  And me propose l'upgrade (ou l'applique si auto-upgrade activé)
```

### Hiérarchie de qualité
```
Audio: MULTI (100) > VF (80) > VOSTFR (60) > VO (40)
Vidéo: 4K HDR (100) > 4K (90) > 1080p HEVC (80) > 1080p x264 (70) > 720p (50)
```

### Conditions d'upgrade
- Gain de score ≥ 20 points
- Seeders ≥ 10
- Espace disque suffisant

### Modèle de données
```python
class MediaQualityProfile(Base):
    id: int
    plex_rating_key: str
    tmdb_id: Optional[int]
    title: str
    current_resolution: str  # 720p, 1080p, 4K
    current_video_codec: str  # x264, hevc, av1
    current_audio_language: str  # VOSTFR, MULTI, VF
    overall_score: int  # 0-100
    upgrade_available: bool = False
    upgrade_type: Optional[str]  # audio, video, both

class UpgradeRule(Base):
    id: int
    name: str
    source_quality: str  # VOSTFR, 720p, x264
    target_quality: str  # MULTI, 1080p, hevc
    min_score_gain: int = 20
    auto_apply: bool = False
    media_types: list  # ["movie", "anime"]
```

---

## 4.3 🤖 Feature 3: Agent IA d'Analyse de Bibliothèque

### Description
Agent IA analysant périodiquement la médiathèque pour générer des rapports, détecter des problèmes, et proposer des améliorations.

### Capacités
1. **Rapport hebdomadaire automatique**
   - Score de santé global (0-100)
   - Problèmes détectés (critiques, importants, mineurs)
   - Upgrades disponibles
   - Collections incomplètes
   - Recommandations priorisées

2. **Analyse qualité technique**
   - Via ffprobe/mediainfo
   - Détection codec obsolète, bitrate faible, HDR

3. **Chat conversationnel**
   - Questions sur la bibliothèque
   - Commandes: `/analyse`, `/cherche`, `/upgrade`, `/rapport`

### Modèle de données
```python
class AIAnalysisReport(Base):
    id: int
    report_type: str  # weekly, monthly, on_demand
    health_score: int  # 0-100
    issues_found: int
    upgrades_available: int
    report_data: dict  # JSON détaillé
    recommendations: list  # JSON

class AIRecommendation(Base):
    id: int
    report_id: Optional[int]
    target_type: str  # media, collection, system
    target_title: str
    recommendation_type: str  # upgrade, download, delete, fix
    priority: str  # critical, high, medium, low
    description: str
    status: str  # pending, approved, applied, rejected
```

---

# 5. ARCHITECTURE V2

## 5.1 Stack Technique

| Composant | V1 | V2 |
|-----------|----|----|
| Backend | FastAPI (mixte) | FastAPI full async |
| Database | SQLite | PostgreSQL |
| Task Queue | asyncio | Celery + Redis |
| Frontend | Vanilla JS | Vue.js 3 + Vite |
| State | Variables globales | Pinia |
| Real-time | Polling | WebSocket |

## 5.2 Diagramme d'architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND (Vue.js 3)                         │
│  [Search] [Requests] [Follows] [Admin] [AI Chat]               │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP/REST + WebSocket
┌─────────────────────────▼───────────────────────────────────────┐
│                    API GATEWAY (FastAPI)                        │
│  [Auth] [Rate Limit] [CORS] [Logging]                          │
│  /auth /search /requests /follows /upgrades /admin /ai         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                     SERVICE LAYER                               │
│  [MediaSearch] [Pipeline] [FollowManager] [UpgradeMonitor]     │
│  [AIAgent] [LibraryAnalyzer] [QualityScorer]                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                  BACKGROUND WORKERS (Celery)                    │
│  [DownloadWorker] [ReleaseChecker] [UpgradeScanner] [AIWorker] │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                      DATA LAYER                                 │
│  [PostgreSQL] [Redis] [File System]                            │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   EXTERNAL SERVICES                             │
│  [TMDB] [AniList] [YGG] [qBit] [Plex] [Ollama/Qwen3-VL]       │
└─────────────────────────────────────────────────────────────────┘
```

## 5.3 Structure des dossiers

```
plex-kiosk-v2/
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── auth.py, search.py, requests.py
│   │   │   ├── follows.py      # 🆕
│   │   │   ├── upgrades.py     # 🆕
│   │   │   └── ai.py           # 🆕
│   │   ├── models/
│   │   │   ├── follow.py, upgrade.py, ai_report.py  # 🆕
│   │   ├── services/
│   │   │   ├── ai/             # 🆕 agent, analyzer, chat
│   │   │   ├── automation/     # 🆕 follow_manager, release_checker
│   │   │   └── quality/        # 🆕 media_analyzer, quality_scorer
│   │   └── workers/            # 🆕 Celery tasks
│   └── alembic/                # 🆕 Migrations
├── frontend/                   # 🆕 Vue.js 3
│   ├── src/
│   │   ├── components/
│   │   ├── views/
│   │   ├── stores/
│   │   └── composables/
└── docker/
```

---

# 6. INTÉGRATIONS IA

## 6.1 Vue d'ensemble

Avec **Qwen3-VL-30B-A3B** (multimodal), nous avons :
- Compréhension texte et images
- Raisonnement complexe
- Analyses structurées
- Conversations contextuelles

## 6.2 Prompt - Scoring Torrents (amélioré)

```python
TORRENT_SCORING_PROMPT = """Tu es un expert en sélection de torrents pour Plex.

## CONTEXTE
Média: {title} ({year}) - Type: {media_type}
Préférences: Qualité={quality_preference}, Langue={language_preference}

## TORRENTS
{torrents_list}

## SCORING (sur 100)
- Audio (40pts): MULTI=40, VFF=30, VOSTFR=20, VO=10
- Vidéo (35pts): 4K HDR=35, 4K=30, 1080p HEVC=25, 1080p x264=20, 720p=10
- Source (15pts): BluRay=15, WEB-DL=12, WEBRip=10, HDTV=5, CAM=-50
- Fiabilité (10pts): Seeders >50=10, >20=7, >10=5, <10=2

## RÉPONSE (JSON strict)
{
  "rankings": [{"index": 1, "score": 85, "reason": "..."}],
  "best_choice": 1,
  "confidence": 0.92
}"""
```

## 6.3 Prompt - Analyse Bibliothèque

```python
LIBRARY_ANALYSIS_PROMPT = """Analyse cette bibliothèque Plex.

## DONNÉES
{library_stats}
{media_samples}
{collections}

## GÉNÈRE
1. Score santé (0-100) avec tendance
2. Problèmes par priorité (critical/important/minor)
3. Upgrades disponibles (VOSTFR→MULTI, résolution, codec)
4. Collections incomplètes
5. Top 5 recommandations

## RÉPONSE (JSON)
{
  "health_score": 78,
  "issues": {"critical": [], "important": [...], "minor": [...]},
  "upgrade_opportunities": {"vostfr_to_multi": [...], "codec_upgrade": [...]},
  "incomplete_collections": [...],
  "recommendations": [{"priority": 1, "action": "...", "target": "..."}]
}"""
```

## 6.4 Prompt - Chat Système

```python
AI_CHAT_SYSTEM_PROMPT = """Tu es l'assistant IA de Plex Kiosk.

## CAPACITÉS
- Répondre sur la bibliothèque
- Exécuter analyses
- Proposer actions (avec confirmation)

## CONTEXTE
User: {username} ({role})
Stats: {library_stats}
Suivis: {followed_series}

## COMMANDES
/analyse [type] - Lance analyse
/cherche [query] - Recherche
/upgrade [media] - Propose upgrade
/rapport - Génère rapport

## RÈGLES
- Français, concis, actions concrètes
- Confirmation avant actions irréversibles"""
```

## 6.5 Intégration Vision (optionnel)

```python
# Vérification poster
POSTER_VERIFICATION_PROMPT = """Compare ces deux posters.
[Image 1: TMDB] [Image 2: Fichier]
Est-ce le même film ? Confiance ?"""

# Détection qualité par screenshot
QUALITY_DETECTION_PROMPT = """Analyse ce screenshot.
Résolution apparente ? Artefacts ? Hardcoded subs ?"""
```

---

# 7. MODÈLES DE DONNÉES

## 7.1 Diagramme ER simplifié

```
Users ──< MediaRequests >── Downloads
  │
  └──< SeriesFollows >── EpisodeReleases

MediaQualityProfiles ──< UpgradeHistory
                    └── UpgradeRules

AIAnalysisReports ──< AIRecommendations

AIConversations (user_id)
```

---

# 8. API ENDPOINTS V2

## 8.1 Suivi séries `/api/v1/follows`

```yaml
POST /follows           # Ajouter au suivi
GET /follows            # Lister mes suivis  
GET /follows/{id}       # Détails + épisodes
PATCH /follows/{id}     # Modifier préférences
DELETE /follows/{id}    # Arrêter suivi
POST /follows/{id}/check # Forcer vérification
GET /follows/calendar   # Calendrier 7 jours
```

## 8.2 Upgrades `/api/v1/upgrades`

```yaml
GET /upgrades/available     # Upgrades disponibles
POST /upgrades/apply/{id}   # Appliquer upgrade
GET /upgrades/rules         # Règles configurées
POST /upgrades/rules        # Créer règle
PATCH /upgrades/rules/{id}  # Modifier règle
DELETE /upgrades/rules/{id} # Supprimer règle
GET /upgrades/history       # Historique
```

## 8.3 Agent IA `/api/v1/ai`

```yaml
POST /ai/analyze                      # Lancer analyse
GET /ai/reports                       # Liste rapports
GET /ai/reports/{id}                  # Détail rapport
GET /ai/recommendations               # Recommandations actives
POST /ai/recommendations/{id}/apply   # Appliquer
POST /ai/recommendations/{id}/dismiss # Rejeter
POST /ai/chat                         # Message chat
GET /ai/chat/{conversation_id}        # Historique
```

## 8.4 WebSocket `/ws`

```yaml
/ws/notifications  # download_progress, new_episode, upgrade_available
/ws/ai/chat        # Streaming chat IA
```

---

# 9. ROADMAP & PHASES

## Phase 0: Assainissement (2 semaines)
- [ ] Backend full async
- [ ] Dependency Injection
- [ ] Alembic + PostgreSQL
- [ ] Celery + Redis
- [ ] CORS sécurisé
- [ ] Frontend Vue.js 3 setup

## Phase 1: Suivi Automatique (3 semaines)
- [ ] Modèles SeriesFollow + EpisodeRelease
- [ ] Service CalendarSync
- [ ] Worker ReleaseChecker
- [ ] API /follows
- [ ] UI FollowsView

## Phase 2: Surveillance Upgrades (3 semaines)
- [ ] Modèles MediaQualityProfile + UpgradeRule
- [ ] Service MediaAnalyzer (ffprobe)
- [ ] Worker UpgradeScanner
- [ ] API /upgrades
- [ ] UI gestion upgrades

## Phase 3: Agent IA (3 semaines)
- [ ] Modèles AIReport + AIRecommendation
- [ ] Service LibraryAnalyzer
- [ ] Service AIChat
- [ ] Worker analyses périodiques
- [ ] UI Dashboard IA + Chat

## Phase 4: Polish (2 semaines)
- [ ] Tests unitaires/intégration
- [ ] Documentation complète
- [ ] Optimisations (cache Redis)
- [ ] Monitoring Prometheus/Grafana

---

# 10. PRÉ-PROMPTS CLAUDE CODE

## 10.1 Phase 0 - Assainissement Backend

```markdown
# CONTEXTE
Tu travailles sur Plex Kiosk. Le code a des problèmes d'architecture à corriger.

# OBJECTIFS
1. Migrer vers full async (supprimer `asyncio.get_event_loop().run_until_complete()`)
2. Implémenter Dependency Injection avec FastAPI Depends
3. Configurer Alembic pour migrations
4. Ajouter support PostgreSQL
5. Sécuriser CORS

# FICHIERS À MODIFIER
- backend/app/main.py
- backend/app/config.py
- backend/app/dependencies.py (créer)
- backend/app/models/database.py
- backend/app/services/*.py
- backend/alembic/ (créer)

# STRUCTURE ATTENDUE
```python
# dependencies.py
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session

async def get_media_search_service(
    settings: Settings = Depends(get_settings)
) -> MediaSearchService:
    return MediaSearchService(settings)
```

# LIVRABLE
Code refactoré, DI configurée, Alembic initialisé, CORS sécurisé
```

## 10.2 Phase 0 - Migration Frontend Vue.js

```markdown
# CONTEXTE
Tu migres le frontend de Vanilla JS vers Vue.js 3.

# CODE EXISTANT
- admin.html (2943 lignes inline)
- static/js/app.js (1530 lignes)

# OBJECTIFS
1. Créer projet Vue 3 + Vite + TypeScript
2. Migrer composants vers Vue SFC
3. Implémenter Pinia stores
4. Configurer Tailwind CSS
5. Client WebSocket

# STRUCTURE CIBLE
```
frontend/src/
├── components/common/, media/, follow/, admin/, ai/
├── views/
├── stores/
├── composables/
└── services/
```

# CONTRAINTES
- Conserver le design Netflix
- Responsive
- TypeScript strict

# LIVRABLE
Projet Vue 3 fonctionnel remplaçant le frontend
```

## 10.3 Phase 1 - Suivi Automatique Séries

```markdown
# CONTEXTE
Tu ajoutes le suivi automatique des séries (type Sonarr).

# OBJECTIFS
1. Modèles SeriesFollow + EpisodeRelease
2. Service CalendarSync (TMDB + AniList + TVMaze)
3. Worker Celery pour checks périodiques
4. Endpoints API /follows/*
5. Composants frontend

# LOGIQUE MÉTIER
1. User suit série → récupérer calendrier → créer EpisodeRelease
2. Worker (toutes 2h): pour chaque episode avec air_date passé + 2h:
   - Rechercher torrent, si score > 70: créer MediaRequest
   - Sinon: réessayer plus tard
3. Timeout 48h → failed, alerter admin

# ENDPOINTS
POST/GET/PATCH/DELETE /follows
POST /follows/{id}/check
GET /follows/calendar

# LIVRABLE
Feature complète et testée
```

## 10.4 Phase 2 - Surveillance Upgrades

```markdown
# CONTEXTE
Tu ajoutes la surveillance et upgrade automatique de qualité.

# OBJECTIFS
1. Modèles MediaQualityProfile, UpgradeRule, UpgradeHistory
2. MediaAnalyzer (ffprobe extraction)
3. UpgradeMonitor
4. Règles auto-upgrade
5. Interface gestion

# SCORING QUALITÉ
```python
def calculate_score(profile):
    score = 0
    # Vidéo (50pts): 4K=50, 1080p=40, 720p=25
    # Audio (40pts): MULTI=40, VF=30, VOSTFR=20
    # Bonus (10pts): HDR, lossless audio
    return score
```

# WORKFLOW
1. Scanner hebdo parcourt MediaQualityProfile
2. Chercher meilleure version sur YGG
3. Si upgrade + règle match → créer UpgradeOpportunity
4. Si auto_apply → lancer téléchargement
5. Après succès → remplacer ancien fichier

# LIVRABLE
Feature complète avec scan auto et interface admin
```

## 10.5 Phase 3 - Agent IA Analyse

```markdown
# CONTEXTE
Tu implémentes l'agent IA d'analyse de bibliothèque (Qwen3-VL-30B-A3B).

# OBJECTIFS
1. Modèles AIAnalysisReport, AIRecommendation, AIConversation
2. LibraryAnalyzer pour analyses auto
3. AIChat pour conversations
4. Worker analyses périodiques
5. Dashboard IA admin

# SERVICES
```python
class LibraryAnalyzerService:
    async def run_full_analysis(self) -> AIAnalysisReport:
        stats = await self._get_library_stats()
        prompt = self._build_analysis_prompt(stats)
        response = await self.ai_service.query(prompt)
        return self._parse_and_save(response)

class AIChatService:
    async def chat(self, message: str, user: User) -> AIChatResponse:
        context = await self._build_context(user)
        if message.startswith("/"):
            return await self._handle_command(message)
        return await self._query_ai(message, context)
```

# CELERY SCHEDULE
```python
beat_schedule = {
    'weekly-analysis': {'task': 'run_weekly_analysis', 
                        'schedule': crontab(hour=6, day_of_week=1)},
    'daily-quality-scan': {'task': 'run_quality_scan',
                           'schedule': crontab(hour=0)},
}
```

# LIVRABLE
Agent IA complet avec analyses auto, chat, et dashboard
```

## 10.6 Phase 4 - Tests & Documentation

```markdown
# CONTEXTE
Phase finale: tests, documentation, optimisations.

# TESTS
```python
# Unit
def test_quality_scorer():
    profile = MediaQualityProfile(resolution="1080p", audio="MULTI")
    assert QualityScorer.calculate_score(profile) >= 80

# Integration
async def test_follow_workflow(client):
    response = await client.post("/follows", json={"tmdb_id": 1399})
    assert response.status_code == 201
```

# DOCUMENTATION
- README.md (installation, config, architecture)
- docs/API.md (endpoints, exemples)
- docs/DEPLOYMENT.md (Docker, SSL, backups)
- docs/AI_INTEGRATION.md (Ollama, prompts)

# OPTIMISATIONS
- Cache Redis (@cached decorator)
- Index DB (upgrade_available, overall_score)
- Lazy loading relations

# MONITORING
- Prometheus metrics
- Grafana dashboards
- Alertes critiques

# LIVRABLE
Application production-ready avec tests et docs
```

---

# 11. ANNEXES

## 11.1 Glossaire

| Terme | Définition |
|-------|------------|
| VOSTFR | Version Originale Sous-Titrée Français |
| MULTI | Plusieurs pistes audio (VF + VO) |
| HEVC/x265 | Codec vidéo haute efficacité |
| Rating Key | ID unique Plex |

## 11.2 Références

- [Sonarr Wiki](https://wiki.servarr.com/sonarr)
- [TMDB API](https://developers.themoviedb.org/3)
- [AniList API](https://anilist.gitbook.io/anilist-apiv2-docs/)
- [Qwen Docs](https://qwen.readthedocs.io/)

---

**Document PRD - Plex Kiosk V2**  
**Prêt pour implémentation avec Claude Code**

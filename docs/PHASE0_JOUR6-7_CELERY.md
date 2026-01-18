## PHASE 0 - JOUR 6-7: Intégration Celery + Redis

**Date**: 2026-01-18
**Statut**: ✅ Complété

## Objectif

Remplacer FastAPI BackgroundTasks par Celery pour le traitement des tâches en arrière-plan avec:
- Persistance des tâches
- Retry automatique sur échec
- Monitoring via Flower
- Tâches périodiques via Celery Beat

---

## Architecture

```
┌────────────────────────────────────────────┐
│  FRONTEND (Vue.js 3) → Nginx               │
├────────────────────────────────────────────┤
│  BACKEND (FastAPI) → uvicorn               │
│   ├─ POST /requests → Queue Celery task    │
│   └─ GET /requests → Check task status     │
├────────────────────────────────────────────┤
│  WORKERS (Celery)                          │
│   ├─ celery-worker (2 concurrency)         │
│   ├─ celery-beat (scheduler)               │
│   └─ flower (monitoring - dev only)        │
├────────────────────────────────────────────┤
│  REDIS                                     │
│   ├─ DB 0: Broker (task queue)             │
│   └─ DB 1: Backend (results)               │
├────────────────────────────────────────────┤
│  POSTGRESQL                                │
│   └─ Persistent data + task tracking       │
└────────────────────────────────────────────┘
```

---

## Changements Effectués

### 1. Configuration Celery

**Fichier**: [backend/app/celery_app.py](backend/app/celery_app.py) (CRÉÉ)

**Configuration**:
- Broker: `redis://redis:6379/0`
- Backend: `redis://redis:6379/1`
- Serialization: JSON
- Timezone: Europe/Paris
- Task time limit: 3600s (1h hard), 3300s (55m soft)
- Worker max tasks per child: 100 (restart après)

**Queues**:
- `default` - Tâches générales
- `priority` - Tâches prioritaires
- `plex_sync` - Synchronisation Plex
- `downloads` - Monitoring téléchargements

**Beat Schedule** (tâches périodiques):
```python
beat_schedule = {
    # Plex sync - every hour
    "plex-sync-hourly": {
        "task": "app.workers.plex_sync_worker.sync_plex_library_task",
        "schedule": crontab(minute=0),
        "kwargs": {"full_sync": False},
    },

    # Full Plex sync - daily at 3 AM
    "plex-sync-daily-full": {
        "task": "app.workers.plex_sync_worker.sync_plex_library_task",
        "schedule": crontab(hour=3, minute=0),
        "kwargs": {"full_sync": True},
    },

    # Monitor downloads - every 5 minutes
    "download-monitor": {
        "task": "app.workers.download_monitor_worker.monitor_downloads_task",
        "schedule": 300.0,
    },

    # Cleanup old downloads - daily at 4 AM
    "cleanup-downloads": {
        "task": "app.workers.cleanup_worker.cleanup_old_downloads_task",
        "schedule": crontab(hour=4, minute=0),
    },

    # Cleanup expired results - daily at 5 AM
    "cleanup-expired-results": {
        "task": "app.workers.cleanup_worker.cleanup_expired_task_results",
        "schedule": crontab(hour=5, minute=0),
    },
}
```

---

### 2. Workers

**Directory**: [backend/app/workers/](backend/app/workers/) (CRÉÉ)

#### a) Request Worker

**Fichier**: [backend/app/workers/request_worker.py](backend/app/workers/request_worker.py)

**Tâches**:
- `process_request_task` - Traiter une requête média complète
  - Search torrents
  - AI selection
  - Queue download
- `complete_request_task` - Finaliser après téléchargement
  - Rename files
  - Transfer to Plex
  - Trigger scan
  - Send notification

**Features**:
- Max retries: 3
- Retry delay: 300s (5 minutes)
- Auto-retry sur erreurs temporaires

#### b) Plex Sync Worker

**Fichier**: [backend/app/workers/plex_sync_worker.py](backend/app/workers/plex_sync_worker.py)

**Tâches**:
- `sync_plex_library_task` - Synchroniser bibliothèque Plex
  - Mode incrémental (hourly)
  - Mode full (daily)
  - Track new items
  - Update existing
  - Remove deleted
- `cleanup_old_sync_data` - Nettoyer anciennes données (30 days)

#### c) Download Monitor Worker

**Fichier**: [backend/app/workers/download_monitor_worker.py](backend/app/workers/download_monitor_worker.py)

**Tâches**:
- `monitor_downloads_task` - Surveiller téléchargements actifs
  - Update progress
  - Detect completion
  - Handle errors
  - Queue completion task
- `cleanup_finished_torrents` - Retirer torrents après seeding

#### d) Cleanup Worker

**Fichier**: [backend/app/workers/cleanup_worker.py](backend/app/workers/cleanup_worker.py)

**Tâches**:
- `cleanup_old_downloads_task` - Nettoyer vieux téléchargements (30 days)
- `cleanup_old_requests_task` - Nettoyer vieilles requêtes (90 days)
- `cleanup_expired_task_results` - Nettoyer résultats Celery expirés
- `database_maintenance_task` - VACUUM ANALYZE (PostgreSQL)
- `cleanup_temp_files_task` - Nettoyer fichiers temporaires

#### e) Workers Init

**Fichier**: [backend/app/workers/__init__.py](backend/app/workers/__init__.py)

Exporte toutes les tâches pour découverte Celery.

---

### 3. Dépendances

**Fichier**: [backend/requirements.txt](backend/requirements.txt)

**Ajouts**:
```txt
celery[redis]==5.4.0  # Background task processing
flower==2.0.1         # Celery monitoring UI
```

---

### 4. Docker Infrastructure

#### a) Dockerfile Worker

**Fichier**: [Dockerfile.worker](Dockerfile.worker) (CRÉÉ)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY backend/app /app/app

# Non-root user
RUN useradd -m -u 1000 celeryuser && \
    chown -R celeryuser:celeryuser /app
USER celeryuser

CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
```

#### b) Docker Compose Services

**Fichier**: [docker-compose.yml](docker-compose.yml)

**Nouveaux services**:

**celery-worker**:
- 2 concurrency workers
- Mêmes env vars que backend
- Volumes: data, downloads, media
- Depends on: postgres, redis

**celery-beat**:
- Scheduler pour tâches périodiques
- Minimal env vars (database + redis)
- Depends on: redis

**flower** (dev only):
- Monitoring UI sur port 5555
- Profile `dev` (start avec `--profile dev`)
- Depends on: redis, celery-worker

---

### 5. API Updates

**Fichier**: [backend/app/api/v1/requests.py](backend/app/api/v1/requests.py)

**Changements**:

**AVANT** (BackgroundTasks):
```python
@router.post("", response_model=RequestResponse)
async def create_request(
    ...,
    background_tasks: BackgroundTasks,
):
    # Create request
    db.add(media_request)
    await db.commit()

    # Process in background (NOT persistent)
    background_tasks.add_task(process_request_background, media_request.id)
```

**APRÈS** (Celery):
```python
@router.post("", response_model=RequestResponse)
async def create_request(
    ...,
    # Removed BackgroundTasks
):
    # Create request
    db.add(media_request)
    await db.commit()

    # Queue Celery task (PERSISTENT + RETRY)
    from ...workers.request_worker import process_request_task
    task = process_request_task.delay(media_request.id)

    # Track task ID
    media_request.celery_task_id = task.id
    await db.commit()
```

---

### 6. Database Migration

**Fichier**: [backend/alembic/versions/20260118_1825_002_add_celery_task_id.py](backend/alembic/versions/20260118_1825_002_add_celery_task_id.py)

**Changements**:
```sql
-- Add celery_task_id column to media_requests
ALTER TABLE media_requests ADD COLUMN celery_task_id VARCHAR(100);
CREATE INDEX ix_media_requests_celery_task_id ON media_requests(celery_task_id);
```

**Utilité**: Tracker task Celery pour chaque request (check status, retry, etc.)

---

## Instructions d'Utilisation

### Démarrage

```bash
# 1. Rebuild workers
docker-compose build celery-worker celery-beat flower

# 2. Appliquer migration
docker-compose exec plex-kiosk alembic upgrade head

# 3. Start all services
docker-compose up -d

# 4. Start with Flower (dev)
docker-compose --profile dev up -d
```

### Vérification

```bash
# Check services
docker-compose ps

# Expected:
# - plex-kiosk (running)
# - postgres (healthy)
# - redis (healthy)
# - celery-worker (running)
# - celery-beat (running)
# - flower (running - if --profile dev)

# Worker logs
docker-compose logs -f celery-worker

# Beat logs
docker-compose logs -f celery-beat

# Flower UI
open http://localhost:5555
```

### Monitoring avec Flower

**URL**: http://localhost:5555

**Features**:
- Task list (running, succeeded, failed)
- Worker status
- Task statistics
- Rate limiting
- Task details (args, kwargs, result, traceback)

---

## Commandes Celery

### Démarrer worker manuellement

```bash
# Dans container
docker-compose exec celery-worker celery -A app.celery_app worker --loglevel=info

# Local (dev)
cd backend
celery -A app.celery_app worker --loglevel=info --concurrency=2
```

### Démarrer beat manuellement

```bash
# Dans container
docker-compose exec celery-beat celery -A app.celery_app beat --loglevel=info

# Local (dev)
cd backend
celery -A app.celery_app beat --loglevel=info
```

### Inspecter tasks

```bash
# List active tasks
celery -A app.celery_app inspect active

# List scheduled tasks (beat)
celery -A app.celery_app inspect scheduled

# List registered tasks
celery -A app.celery_app inspect registered

# Worker stats
celery -A app.celery_app inspect stats
```

### Purger queue

```bash
# Purger TOUTES les tasks en attente (DANGER!)
celery -A app.celery_app purge

# Confirmer: yes
```

---

## Différences BackgroundTasks vs Celery

| Feature | BackgroundTasks | Celery |
|---------|----------------|--------|
| **Persistance** | ❌ Perdu si restart | ✅ Redis backend |
| **Retry** | ❌ Non | ✅ Configurable (3x) |
| **Monitoring** | ❌ Logs only | ✅ Flower UI |
| **Tâches périodiques** | ❌ Non | ✅ Celery Beat |
| **Scaling** | ❌ Lié au backend | ✅ Workers indépendants |
| **Task status** | ❌ Non trackable | ✅ Task ID + status |
| **Error handling** | ❌ Silent fail | ✅ Retry + notifications |

---

## Workflow Exemple

### Création d'une requête

```
1. User: POST /api/v1/requests
   ↓
2. Backend:
   - Créer MediaRequest (status=PENDING)
   - Queue Celery task
   - Store task.id
   - Return 201 Created
   ↓
3. Celery Worker (request_worker):
   - Search torrents
   - AI selection
   - Queue download
   - Update status=DOWNLOADING
   ↓
4. Celery Beat (every 5 min):
   - Monitor downloads
   - Update progress
   ↓
5. Download completes:
   - Queue completion task
   ↓
6. Celery Worker (complete_request_task):
   - Rename files
   - Transfer to Plex
   - Trigger scan
   - Update status=COMPLETED
   - Send notification
```

---

## Troubleshooting

### Worker ne démarre pas

```bash
# Check logs
docker-compose logs celery-worker

# Common issues:
# - Redis non accessible
# - Import errors (code broken)
# - Missing dependencies

# Rebuild
docker-compose build celery-worker
docker-compose up -d celery-worker
```

### Tasks ne s'exécutent pas

```bash
# Check if worker receives tasks
celery -A app.celery_app inspect active

# Check if broker is accessible
docker-compose exec celery-worker python -c "from app.celery_app import celery_app; print(celery_app.broker_connection().ensure_connection(max_retries=1))"

# Check Redis
docker-compose exec redis redis-cli ping
```

### Beat ne schedule pas

```bash
# Check beat logs
docker-compose logs -f celery-beat

# Verify schedule
celery -A app.celery_app inspect scheduled

# Check if beat is running
docker-compose ps celery-beat
```

### Flower ne charge pas

```bash
# Check if started with profile
docker-compose --profile dev ps

# Access logs
docker-compose logs flower

# Restart
docker-compose --profile dev up -d flower
```

---

## Tâches Périodiques Configurées

| Tâche | Schedule | Description |
|-------|----------|-------------|
| `plex-sync-hourly` | Every hour (minute=0) | Sync incrémental Plex |
| `plex-sync-daily-full` | Daily 3 AM | Sync complet Plex |
| `download-monitor` | Every 5 minutes | Monitor downloads actifs |
| `cleanup-downloads` | Daily 4 AM | Nettoyer vieux downloads (30d) |
| `cleanup-expired-results` | Daily 5 AM | Nettoyer résultats Celery |

---

## Sécurité

**Non-root user**: Worker tourne avec `celeryuser` (UID 1000)

**Network isolation**: Workers dans réseau Docker privé

**Resource limits**:
- Worker max memory: 400MB per child
- Worker max tasks: 100 per child (restart)
- Task time limit: 1h hard, 55m soft

---

## Prochaines Étapes

- ✅ JOUR 6-7 terminé
- ⏭️ **JOUR 8**: Sécuriser CORS
  - Remplacer `allow_origins=["*"]`
  - Configurer origines autorisées
  - Environment variables

---

## Fichiers Créés/Modifiés (Résumé)

### Créés:
- [backend/app/celery_app.py](backend/app/celery_app.py)
- [backend/app/workers/__init__.py](backend/app/workers/__init__.py)
- [backend/app/workers/request_worker.py](backend/app/workers/request_worker.py)
- [backend/app/workers/plex_sync_worker.py](backend/app/workers/plex_sync_worker.py)
- [backend/app/workers/download_monitor_worker.py](backend/app/workers/download_monitor_worker.py)
- [backend/app/workers/cleanup_worker.py](backend/app/workers/cleanup_worker.py)
- [Dockerfile.worker](Dockerfile.worker)
- [backend/alembic/versions/20260118_1825_002_add_celery_task_id.py](backend/alembic/versions/20260118_1825_002_add_celery_task_id.py)
- [docs/PHASE0_JOUR6-7_CELERY.md](docs/PHASE0_JOUR6-7_CELERY.md) (ce fichier)

### Modifiés:
- [backend/requirements.txt](backend/requirements.txt) - + celery, flower
- [docker-compose.yml](docker-compose.yml) - + celery-worker, celery-beat, flower
- [backend/app/api/v1/requests.py](backend/app/api/v1/requests.py) - BackgroundTasks → Celery
- [backend/app/models/request.py](backend/app/models/request.py) - + celery_task_id

---

**Auteur**: Claude Code
**Phase**: Phase 0 - Assainissement
**Statut**: ✅ Complété

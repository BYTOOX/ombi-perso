# PHASE 0 - JOUR 5: Migration PostgreSQL + Alembic

**Date**: 2026-01-18
**Statut**: ✅ Complété

## Objectif

Migrer de SQLite vers PostgreSQL avec gestion de migrations via Alembic.

---

## Changements Effectués

### 1. Dépendances Python

**Fichier**: `backend/requirements.txt`

Ajout de:
```txt
alembic==1.13.1           # Database migrations
asyncpg==0.29.0           # PostgreSQL async driver (runtime)
psycopg2-binary==2.9.9    # PostgreSQL sync driver (Alembic)
```

### 2. Configuration Application

**Fichier**: `backend/app/config.py`

- URL par défaut changée de SQLite → PostgreSQL
- Nouvelle URL: `postgresql+asyncpg://postgres:postgres@localhost:5432/plex_kiosk_dev`

### 3. Configuration Database

**Fichier**: `backend/app/models/database.py`

**Changements majeurs**:
- ✅ Détection automatique PostgreSQL vs SQLite
- ✅ Async engine avec `asyncpg` pour runtime
- ✅ Sync engine avec `psycopg2` pour migrations
- ✅ Connection pooling configuré:
  - `pool_size=10`
  - `max_overflow=20`
  - `pool_recycle=3600` (1h)
  - `pool_pre_ping=True` (vérifie connexions)
- ❌ **SUPPRIMÉ**: `init_db()` fonction (remplacé par Alembic)

### 4. Infrastructure Alembic

#### Fichier: `backend/alembic.ini`

Configuration:
- Script location: `alembic/`
- Template filename: `%%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s`
- Timezone: `Europe/Paris`
- Logging configuré

#### Fichier: `backend/alembic/env.py`

Configuration environnement:
- Import de TOUS les modèles SQLAlchemy
- Support async migrations avec `async_engine_from_config`
- Modes offline et online
- Détection auto du `DATABASE_URL` depuis config
- Conversion automatique: `sqlite+aiosqlite` → `sqlite://` et `postgresql+asyncpg` → `postgresql+psycopg2://`

#### Fichier: `backend/alembic/script.py.mako`

Template pour générer les migrations.

#### Fichier: `backend/alembic/versions/20260118_1810_001_initial_migration.py`

Migration initiale créée manuellement avec:
- ✅ Toutes les tables existantes
- ✅ Index pour performance
- ✅ Foreign keys avec `ON DELETE CASCADE`
- ✅ Utilisateur admin par défaut:
  - Username: `admin`
  - Password: `admin` (hash Argon2)
  - Email: `admin@plex-kiosk.local`
  - Role: `admin`

**Tables créées**:
1. `users` - Utilisateurs
2. `media_requests` - Requêtes média
3. `downloads` - Téléchargements
4. `plex_library_items` - Bibliothèque Plex
5. `rename_settings` - Paramètres renommage
6. `title_mappings` - Mappings titres FR/EN
7. `system_settings` - Paramètres système
8. `transfer_history` - Historique transferts

### 5. Docker Compose

**Fichier**: `docker-compose.yml`

#### Nouveau service `postgres`:
```yaml
postgres:
  image: postgres:16-alpine
  container_name: plex-kiosk-postgres
  environment:
    POSTGRES_DB: plex_kiosk
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
  volumes:
    - postgres-data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres"]
    interval: 10s
```

#### Service `plex-kiosk` modifié:
- `DATABASE_URL` → PostgreSQL
- `depends_on` avec health checks:
  - `postgres: condition: service_healthy`
  - `redis: condition: service_healthy`

#### Nouveau volume:
- `postgres-data` - Persistance données PostgreSQL

### 6. Environment Variables

**Fichier**: `.env.example`

Ajout de:
```bash
# Database (PostgreSQL recommended for production)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/plex_kiosk_dev
POSTGRES_PASSWORD=postgres
```

### 7. Script de Test

**Fichier**: `backend/test_db_connection.py`

Script pour valider:
1. Connexion async PostgreSQL
2. Présence des tables
3. Existence de l'utilisateur admin

---

## Instructions d'Utilisation

### Démarrage Fresh Start

```bash
# 1. Arrêter containers existants
docker-compose down -v

# 2. Créer fichier .env (si pas déjà fait)
cp .env.example .env
# Éditer .env et remplir SECRET_KEY + autres variables

# 3. Démarrer PostgreSQL
docker-compose up -d postgres

# 4. Attendre que PostgreSQL soit prêt
docker-compose logs -f postgres
# Attendre: "database system is ready to accept connections"

# 5. Appliquer migrations
cd backend
alembic upgrade head

# 6. Tester connexion
python test_db_connection.py

# 7. Démarrer tous les services
cd ..
docker-compose up -d
```

### Vérification

```bash
# Vérifier que PostgreSQL tourne
docker-compose ps postgres

# Voir logs PostgreSQL
docker-compose logs -f postgres

# Tester connexion depuis host
PGPASSWORD=postgres psql -h localhost -U postgres -d plex_kiosk -c "\dt"

# Vérifier tables créées
PGPASSWORD=postgres psql -h localhost -U postgres -d plex_kiosk -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"

# Vérifier admin user
PGPASSWORD=postgres psql -h localhost -U postgres -d plex_kiosk -c "SELECT username, email, role FROM users;"
```

### Connexion à l'Application

1. Accéder à: http://localhost:8765
2. Credentials par défaut:
   - Username: `admin`
   - Password: `admin`
3. **IMPORTANT**: Changer le mot de passe immédiatement!

---

## Commandes Alembic

### Créer une nouvelle migration

```bash
cd backend

# Auto-générer depuis modèles
alembic revision --autogenerate -m "Description des changements"

# Créer migration vide
alembic revision -m "Description"

# Éditer le fichier généré dans alembic/versions/
```

### Appliquer migrations

```bash
# Appliquer toutes les migrations
alembic upgrade head

# Appliquer 1 migration
alembic upgrade +1

# Appliquer jusqu'à une révision spécifique
alembic upgrade <revision_id>
```

### Annuler migrations

```bash
# Annuler 1 migration
alembic downgrade -1

# Annuler toutes les migrations
alembic downgrade base
```

### Informations

```bash
# Voir historique migrations
alembic history

# Voir migration actuelle
alembic current

# Voir différences entre DB et modèles
alembic check
```

---

## Troubleshooting

### Erreur: "ModuleNotFoundError: No module named 'asyncpg'"

```bash
cd backend
pip install -r requirements.txt
```

### Erreur: "could not connect to server"

Vérifier que PostgreSQL est démarré:
```bash
docker-compose up -d postgres
docker-compose logs postgres
```

### Erreur: "relation 'users' does not exist"

Appliquer les migrations:
```bash
cd backend
alembic upgrade head
```

### Reset complet de la DB

```bash
# ATTENTION: Perd toutes les données!
docker-compose down -v
docker volume rm plex-kiosk_postgres-data
docker-compose up -d postgres
cd backend
alembic upgrade head
```

### Voir structure DB

```bash
# Connexion interactive
docker-compose exec postgres psql -U postgres -d plex_kiosk

# Dans psql:
\dt              # Lister tables
\d users         # Décrire table users
\di              # Lister index
\df              # Lister fonctions
\q               # Quitter
```

---

## Migration de SQLite vers PostgreSQL (si nécessaire)

Si vous avez des données SQLite à migrer:

```bash
# 1. Installer pgloader
brew install pgloader  # macOS
# ou apt install pgloader  # Linux

# 2. Créer fichier migration.load
cat > migration.load <<EOF
LOAD DATABASE
  FROM sqlite://./data/kiosk.db
  INTO postgresql://postgres:postgres@localhost:5432/plex_kiosk
  WITH data only, include no drop, create no tables
  ALTER SCHEMA 'main' RENAME TO 'public';
EOF

# 3. Appliquer migrations Alembic AVANT
cd backend
alembic upgrade head

# 4. Exécuter migration
pgloader migration.load
```

**Note**: Phase 0 recommande un fresh start (pas de migration de données).

---

## Prochaines Étapes

- ✅ JOUR 5 terminé
- ⏭️ **JOUR 6-7**: Intégration Celery + Redis workers
  - Créer `backend/app/celery_app.py`
  - Créer workers (request, plex_sync, download_monitor, cleanup)
  - Docker Compose pour Celery + Flower
  - Remplacer `BackgroundTasks` par Celery tasks

---

## Fichiers Modifiés (Résumé)

```
backend/
  requirements.txt                    # + asyncpg, psycopg2, alembic
  app/
    config.py                         # DATABASE_URL → PostgreSQL
    models/
      database.py                     # Refactor complet
  alembic.ini                         # CRÉÉ
  alembic/
    env.py                            # CRÉÉ
    script.py.mako                    # CRÉÉ
    versions/
      20260118_1810_001_initial_migration.py  # CRÉÉ
  test_db_connection.py               # CRÉÉ

docker-compose.yml                    # + postgres service
.env.example                          # + POSTGRES_PASSWORD

docs/
  PHASE0_JOUR5_POSTGRESQL.md         # CRÉÉ (ce fichier)
```

---

**Auteur**: Claude Code
**Phase**: Phase 0 - Assainissement
**Statut**: ✅ Complété

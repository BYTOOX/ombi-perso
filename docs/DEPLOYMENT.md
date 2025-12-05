# Déploiement Plex Kiosk

Guide de déploiement sur Debian/Synology avec Docker.

## Prérequis

- Docker Engine 20.10+
- Docker Compose v2+
- 2GB RAM minimum (FlareSolverr utilise ~500MB)
- Accès aux services externes (Ollama, qBittorrent, Plex)

## Installation Debian/Ubuntu

### 1. Installer Docker

```bash
# Mise à jour système
sudo apt update && sudo apt upgrade -y

# Installer Docker
curl -fsSL https://get.docker.com | sudo sh

# Ajouter l'utilisateur au groupe docker
sudo usermod -aG docker $USER
newgrp docker

# Installer Docker Compose
sudo apt install docker-compose-plugin -y

# Vérifier
docker --version
docker compose version
```

### 2. Cloner le projet

```bash
git clone https://github.com/votre-repo/ombi-perso.git
cd ombi-perso
```

### 3. Configurer l'environnement

```bash
# Copier le template
cp .env.example .env

# Éditer la configuration
nano .env
```

**Configuration minimale requise :**

```env
# Secret key (générer avec: openssl rand -hex 32)
SECRET_KEY=votre_cle_secrete_ici

# TMDB API Key (https://www.themoviedb.org/settings/api)
TMDB_API_KEY=votre_cle_tmdb

# YGGtorrent
YGG_USERNAME=votre_username
YGG_PASSWORD=votre_password
YGG_PASSKEY=votre_passkey

# Plex (token: https://www.plex.tv/claim/)
PLEX_URL=http://192.168.1.X:32400
PLEX_TOKEN=votre_token_plex

# qBittorrent
QBITTORRENT_URL=http://192.168.1.X:8080
QBITTORRENT_USERNAME=admin
QBITTORRENT_PASSWORD=votre_password

# Ollama (si sur la même machine)
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:14b

# Chemins (adapter à votre config)
DOWNLOAD_PATH=/srv/downloads
MEDIA_PATH=/srv/media
LIBRARY_PATHS={"movie": "/media/Films", "series": "/media/Séries", "anime": "/media/Animés"}

# Discord notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### 4. Créer les dossiers

```bash
mkdir -p data downloads
sudo chown -R 1000:1000 data downloads

# Si accès aux médias Plex
sudo chmod 755 /chemin/vers/media
```

### 5. Lancer le stack

```bash
# Build et démarrage
docker compose up -d

# Vérifier les logs
docker compose logs -f

# Vérifier que tout tourne
docker compose ps
```

### 6. Premier accès

1. Ouvrir `http://votre-ip:8765`
2. Créer le premier compte (sera admin automatiquement)
3. Configurer les librairies dans Admin > Configuration

## Installation Synology (Docker)

### Via Container Manager (DSM 7.2+)

1. **Ouvrir Container Manager** > **Project**
2. **Create** > **Create project**
3. Nommer le projet `plex-kiosk`
4. Sélectionner le chemin du projet cloné
5. Le `docker-compose.yml` sera détecté automatiquement
6. Configurer les variables d'environnement dans l'interface
7. **Build** puis **Start**

### Via SSH (méthode avancée)

```bash
# Connexion SSH
ssh admin@synology

# Accéder au dossier partagé docker
cd /volume1/docker/plex-kiosk

# Lancer
sudo docker compose up -d
```

## Configuration des services

### Ollama (IA locale)

Si Ollama n'est pas installé :

```bash
# Sur Linux
curl -fsSL https://ollama.com/install.sh | sh

# Télécharger le modèle
ollama pull qwen2.5:14b

# Vérifier qu'il tourne
ollama list
```

### qBittorrent

1. Activer Web UI dans Options > Web UI
2. Configurer un port (défaut: 8080)
3. Créer la catégorie `plex-kiosk`
4. Désactiver "Bypass authentication for localhost"

### Plex

Récupérer le token :
1. Ouvrir app.plex.tv dans le navigateur
2. Inspecter le réseau (F12) 
3. Chercher une requête contenant `X-Plex-Token`

## Vérification

```bash
# Vérifier les services
curl http://localhost:8765/api/health

# Tester FlareSolverr
curl -X POST http://localhost:8191/v1 \
  -H "Content-Type: application/json" \
  -d '{"cmd": "request.get", "url": "https://www.google.com"}'
```

## Mise à jour

```bash
git pull
docker compose build --no-cache
docker compose up -d
```

## Troubleshooting

### FlareSolverr ne démarre pas
- Vérifier la RAM disponible (minimum 500MB)
- Augmenter le timeout dans docker-compose.yml

### Erreur de connexion Plex
- Vérifier que le token n'a pas expiré
- Tester avec `curl http://plex-ip:32400?X-Plex-Token=xxx`

### YGGtorrent bloqué
- Vérifier les credentials
- Attendre 5 min (rate limiting)
- Vérifier le passkey

### Base de données corrompue
```bash
# Backup et reset
mv data/kiosk.db data/kiosk.db.bak
docker compose restart plex-kiosk
```

## Ports utilisés

| Service | Port | Description |
|---------|------|-------------|
| plex-kiosk | 8765 | Application web |
| redis | 6379 | Cache (interne) |
| flaresolverr | 8191 | CF bypass |

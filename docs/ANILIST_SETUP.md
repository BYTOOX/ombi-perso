# Configuration AniList

Guide pour configurer l'intégration AniList dans Plex Kiosk.

## Bonne nouvelle !

**AniList utilise une API GraphQL publique qui ne nécessite pas de clé API** pour les opérations de lecture (recherche, détails).

L'application est pré-configurée pour fonctionner avec AniList sans configuration supplémentaire.

## Fonctionnalités

- Recherche d'animés par titre (japonais, anglais, romaji)
- Détails complets (synopsis, genres, studios, score)
- Images haute qualité (posters, bannières)
- Recommandations
- Lien vers MAL (MyAnimeList) si disponible

## API GraphQL

L'endpoint utilisé : `https://graphql.anilist.co`

Exemple de requête de recherche :

```graphql
query {
  Page(page: 1, perPage: 20) {
    media(search: "Attack on Titan", type: ANIME) {
      id
      title {
        romaji
        english
        native
      }
      coverImage {
        large
      }
      averageScore
      genres
    }
  }
}
```

## Limites de rate

AniList impose des limites :
- 90 requêtes par minute
- L'application gère automatiquement le cache pour minimiser les requêtes

## Authentification (optionnel)

Si vous souhaitez accéder aux listes personnelles d'un utilisateur AniList :

1. Créer une application sur https://anilist.co/settings/developer
2. Récupérer le Client ID
3. Ajouter dans `.env` :
   ```
   ANILIST_CLIENT_ID=votre_client_id
   ```

> Note : Cette fonctionnalité n'est pas implémentée dans la v1.0

## Mapping vers Plex

L'application route automatiquement les animés vers la librairie configurée :

```env
LIBRARY_PATHS={"anime": "/media/Animé (JAP)"}
```

## Nommage des fichiers

Le module IA génère des noms compatibles Plex/Filebot :

```
Animé (JAP)/
└── Attack on Titan (2013)/
    └── Season 01/
        ├── Attack on Titan (2013) - S01E01 - To You, in 2000 Years.mkv
        └── Attack on Titan (2013) - S01E02 - That Day.mkv
```

## MyAnimeList (MAL)

L'application récupère automatiquement l'ID MAL depuis AniList pour :
- Améliorer la recherche de torrents
- Permettre des recherches alternatives

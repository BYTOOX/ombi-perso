# PHASE 0 - JOUR 9-10: Setup Vue.js 3 + Vite + Pinia + TypeScript

**Date**: 2026-01-18
**Statut**: ✅ Complété

## Objectif

Créer une nouvelle infrastructure frontend moderne avec Vue.js 3, Vite, Pinia et TypeScript pour remplacer le monolithe JavaScript vanilla.

---

## Problème Identifié

### Frontend actuel (V1):

```
frontend/
├── index.html         # 500 lignes
├── admin.html         # 2,942 lignes (❌ MONOLITHIQUE)
├── requests.html      # 800 lignes
├── static/
│   ├── app.js         # 1,530 lignes (❌ SANS STRUCTURE)
│   └── admin.js       # 1,200 lignes (❌ SANS STRUCTURE)
```

**Problèmes**:
- ❌ Pas de composants réutilisables
- ❌ Pas de state management
- ❌ Pas de routing côté client
- ❌ Pas de types (JavaScript vanilla)
- ❌ Maintenance difficile
- ❌ Tests impossibles
- ❌ Duplication de code massive

---

## Solution: Vue.js 3 Stack Moderne

```
frontend-v2/
├── src/
│   ├── components/    # Composants réutilisables
│   ├── stores/        # Pinia stores (state)
│   ├── services/      # API client
│   ├── router/        # Vue Router
│   ├── types/         # TypeScript types
│   ├── views/         # Pages
│   └── assets/        # Styles
├── vite.config.ts     # Build configuration
├── tsconfig.json      # TypeScript configuration
└── package.json       # Dependencies
```

---

## Stack Technique

| Technology | Version | Rôle |
|------------|---------|------|
| **Vue.js** | 3.4.15 | Framework progressif |
| **Vite** | 5.0.11 | Build tool + dev server |
| **Pinia** | 2.1.7 | State management |
| **TypeScript** | 5.3.3 | Type safety |
| **Vue Router** | 4.2.5 | Client-side routing |
| **Axios** | 1.6.5 | HTTP client |

---

## Structure Créée

### 1. Configuration Files

#### a) `package.json`

**Dependencies**:
```json
{
  "dependencies": {
    "vue": "^3.4.15",
    "vue-router": "^4.2.5",
    "pinia": "^2.1.7",
    "axios": "^1.6.5"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.3",
    "typescript": "~5.3.3",
    "vite": "^5.0.11",
    "vue-tsc": "^1.8.27",
    "eslint": "^8.56.0",
    "prettier": "^3.2.4"
  }
}
```

**Scripts**:
- `npm run dev` - Dev server (localhost:5173)
- `npm run build` - Build production
- `npm run type-check` - TypeScript validation
- `npm run lint` - ESLint
- `npm run format` - Prettier

#### b) `vite.config.ts`

**Features**:
```typescript
{
  // Path aliases
  alias: { '@': './src' },

  // Dev server
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8765'  // Proxy to backend
    }
  },

  // Build optimization
  build: {
    outDir: '../frontend',  // Replace old frontend
    manualChunks: {
      'vue-vendor': ['vue', 'vue-router', 'pinia'],
      'axios-vendor': ['axios']
    }
  }
}
```

#### c) `tsconfig.json`

**Configuration TypeScript**:
- Target: ES2020
- Strict mode enabled
- Path aliases: `@/*` → `./src/*`
- DOM types included

### 2. Application Entry

#### `src/main.ts`

```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
```

#### `src/App.vue`

Root component avec:
- RouterView pour rendering pages
- Auto-restoration session (localStorage)
- Global styles

### 3. Routing (Vue Router)

#### `src/router/index.ts`

**Routes configurées**:
```typescript
{
  path: '/',           // Home (public)
  path: '/login',      // Login (guest only)
  path: '/search',     // Search (auth required)
  path: '/requests',   // My requests (auth required)
  path: '/admin',      // Admin (admin required)
}
```

**Navigation guards**:
- `requiresAuth` - Redirect to login if not authenticated
- `requiresAdmin` - Redirect to home if not admin
- `requiresGuest` - Redirect to home if already authenticated

### 4. State Management (Pinia)

#### a) Auth Store (`stores/auth.ts`)

**State**:
```typescript
{
  token: string | null
  user: User | null
  loading: boolean
  error: string | null
}
```

**Getters**:
- `isAuthenticated` - Check if user logged in
- `isAdmin` - Check if user is admin

**Actions**:
- `login(username, password)` - Login user
- `logout()` - Logout user
- `fetchCurrentUser()` - Get current user info
- `setToken(token)` - Set token + fetch user

#### b) Search Store (`stores/search.ts`)

**State**:
```typescript
{
  results: SearchResult[]
  loading: boolean
  error: string | null
  lastQuery: string
  selectedMediaType: string
}
```

**Actions**:
- `search(query, mediaType)` - Search media
- `clearResults()` - Clear results

#### c) Requests Store (`stores/requests.ts`)

**State**:
```typescript
{
  requests: MediaRequest[]
  loading: boolean
  error: string | null
}
```

**Getters**:
- `pendingRequests` - Filter pending
- `completedRequests` - Filter completed
- `failedRequests` - Filter failed

**Actions**:
- `fetchMyRequests()` - Get user requests
- `fetchAllRequests()` - Get all requests (admin)
- `createRequest(data)` - Create new request
- `cancelRequest(id)` - Cancel request

#### d) Admin Store (`stores/admin.ts`)

**State**:
```typescript
{
  stats: Stats | null
  users: any[]
  settings: any
  loading: boolean
  error: string | null
}
```

**Actions**:
- `fetchStats()` - Get system stats
- `fetchUsers()` - Get all users
- `fetchSettings()` - Get settings
- `updateSettings(settings)` - Update settings

### 5. API Client (Axios)

#### `src/services/api.ts`

**Features**:
- Singleton instance
- Auto-injection JWT token (request interceptor)
- Auto-redirect on 401 (response interceptor)
- Error handling + normalization
- Type-safe methods

**Methods**:
```typescript
// Auth
login(username, password)
logout()
getCurrentUser()

// Search
searchMedia(query, mediaType)

// Requests
createRequest(data)
getMyRequests()
getAllRequests()
getRequest(id)
cancelRequest(id)

// Plex
getPlexLibrary(mediaType, limit, offset)
searchPlexLibrary(query)
syncPlexLibrary(fullSync)

// Admin
getStats()
getUsers()
getSettings()
updateSettings(settings)
```

### 6. TypeScript Types

#### `src/types/api.ts`

**Interfaces définies**:
```typescript
User              # User model
LoginResponse     # Login response
MediaRequest      # Media request model
RequestStatus     # Request status enum
SearchResult      # Search result
PlexLibraryItem   # Plex library item
Stats             # System statistics
ApiError          # API error response
```

### 7. Views (Pages)

#### a) `views/Home.vue`

- Welcome page
- Links to search/requests/admin
- Shows username if authenticated

#### b) `views/Login.vue`

- Login form
- Username + password fields
- Error display
- Redirect after login
- Hint: `admin / admin`

#### c) `views/Search.vue`

- Search bar
- Media type filter
- Results grid (stub - JOUR 11-13)
- Loading state
- Error handling

#### d) `views/MyRequests.vue`

- User's requests list
- Filter by status
- Cancel requests
- Empty state with link to search

#### e) `views/Admin.vue`

- System statistics cards
- User management (stub - JOUR 11-13)
- Settings management (stub - JOUR 11-13)

### 8. Styles

#### `src/assets/main.css`

**CSS Variables**:
```css
:root {
  /* Colors */
  --primary-color: #e5a00d
  --bg-dark: #0f0f0f
  --bg-card: #1a1a1a
  --text-primary: #ffffff

  /* Spacing */
  --spacing-xs to --spacing-2xl

  /* Border radius */
  --radius-sm to --radius-xl

  /* Transitions */
  --transition-fast to --transition-slow
}
```

**Utility classes**:
- `.container` - Max-width container
- `.btn` / `.btn-primary` / `.btn-secondary` - Buttons
- `.card` - Card component
- `.input` - Form inputs
- `.spinner` - Loading spinner

---

## Installation & Usage

### 1. Install Dependencies

```bash
cd frontend-v2
npm install
```

### 2. Development

```bash
npm run dev
```

**Vite dev server starts on**: http://localhost:5173

**Features**:
- Hot Module Replacement (HMR)
- Fast refresh
- TypeScript checking
- API proxy to backend

### 3. Build for Production

```bash
npm run build
```

**Output**: `../frontend/` (replaces old frontend)

**Optimizations**:
- Minification
- Tree-shaking
- Code splitting
- Vendor chunks

### 4. Type Checking

```bash
npm run type-check
```

Validates TypeScript without emitting files.

### 5. Linting & Formatting

```bash
# Lint
npm run lint

# Format
npm run format
```

---

## Integration Backend

### CORS Configuration

Backend must allow frontend origin.

**Development** (automatic):
```bash
# .env (backend)
DEBUG=true
# Allows localhost:5173 automatically
```

**Production**:
```bash
# .env (backend)
DEBUG=false
FRONTEND_URL=https://plex-kiosk.yourdomain.com
```

### API Proxy (Development)

Vite proxies `/api` to backend:

```
Frontend: http://localhost:5173/api/v1/auth/login
   ↓ (proxy)
Backend:  http://localhost:8765/api/v1/auth/login
```

**Benefits**:
- No CORS issues in development
- Same-origin requests
- Simplified configuration

---

## Features Implémentées

### ✅ Authentication Flow

1. User visits `/login`
2. Enters credentials
3. `authStore.login()` called
4. API request via `api.login()`
5. Token + user stored
6. Redirect to home or intended route
7. Token persisted in localStorage

### ✅ Protected Routes

```typescript
router.beforeEach((to, from, next) => {
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next('/login')
  } else if (to.meta.requiresAdmin && !authStore.isAdmin) {
    next('/')
  } else {
    next()
  }
})
```

### ✅ State Persistence

```typescript
// App.vue - onMounted
const token = localStorage.getItem('token')
if (token) {
  authStore.setToken(token)  // Restores session
}
```

### ✅ Error Handling

```typescript
// API interceptor
client.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)
```

---

## Avantages vs V1

| Feature | V1 (Vanilla JS) | V2 (Vue.js 3) |
|---------|-----------------|---------------|
| **Réutilisation** | ❌ Duplication code | ✅ Composants |
| **State management** | ❌ Variables globales | ✅ Pinia stores |
| **Routing** | ❌ Reload pages | ✅ SPA routing |
| **Types** | ❌ Pas de types | ✅ TypeScript |
| **Build** | ❌ Pas d'optimisation | ✅ Vite minify + split |
| **Dev experience** | ❌ Pas de HMR | ✅ HMR + Fast refresh |
| **Tests** | ❌ Impossible | ✅ Testable |
| **Maintenance** | ❌ Difficile | ✅ Facile |

---

## Prochaines Étapes

### JOUR 11-13: Migration Composants

**À migrer depuis V1**:

1. **Media Search** (`admin.html` lignes 450-550):
   - `SearchBar.vue` - Input + filters
   - `MediaCard.vue` - Result card avec poster
   - `MediaDetails.vue` - Details modal

2. **Requests** (`requests.html` lignes 200-400):
   - `RequestList.vue` - List avec filters
   - `RequestCard.vue` - Single request
   - `StatusBadge.vue` - Status chip

3. **Admin** (`admin.html` lignes 100-2942):
   - `Dashboard.vue` - Stats + charts
   - `UserManagement.vue` - Users table
   - `Settings.vue` - Settings forms
   - `PathSettings.vue` - Library paths

4. **Common**:
   - `Navbar.vue` - Navigation
   - `Footer.vue` - Footer
   - `LoadingSpinner.vue` - Loading state
   - `ErrorMessage.vue` - Error display
   - `Modal.vue` - Modal dialog

---

## Troubleshooting

### Cannot connect to API

1. Check backend running: `curl http://localhost:8765/api/health`
2. Check Vite proxy in `vite.config.ts`
3. Check CORS in backend `main.py`

### Type errors

```bash
npm run type-check
```

Fix types in `src/types/api.ts`.

### Build fails

```bash
rm -rf node_modules package-lock.json
npm install
npm run build
```

### Hot reload not working

Restart Vite dev server:
```bash
npm run dev
```

---

## Fichiers Créés (Résumé)

### Configuration (9 fichiers):
- `package.json`
- `vite.config.ts`
- `tsconfig.json`
- `tsconfig.node.json`
- `.eslintrc.cjs`
- `.prettierrc.json`
- `index.html`
- `.gitignore`
- `README.md`

### Source Code (16 fichiers):
- `src/main.ts`
- `src/App.vue`
- `src/assets/main.css`
- `src/router/index.ts`
- `src/types/api.ts`
- `src/services/api.ts`
- `src/stores/auth.ts`
- `src/stores/search.ts`
- `src/stores/requests.ts`
- `src/stores/admin.ts`
- `src/views/Home.vue`
- `src/views/Login.vue`
- `src/views/Search.vue`
- `src/views/MyRequests.vue`
- `src/views/Admin.vue`

**Total**: 25 fichiers créés

---

**Auteur**: Claude Code
**Phase**: Phase 0 - Assainissement
**Statut**: ✅ Complété

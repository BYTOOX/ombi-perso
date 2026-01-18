# Plex Kiosk - Frontend V2

Vue.js 3 + Vite + Pinia + TypeScript frontend for Plex Kiosk.

## Tech Stack

- **Vue.js 3.4** - Progressive JavaScript framework
- **Vite 5** - Next generation frontend tooling
- **Pinia 2** - Vue Store (state management)
- **TypeScript** - Type safety
- **Vue Router 4** - Client-side routing
- **Axios** - HTTP client

## Project Structure

```
frontend-v2/
├── src/
│   ├── assets/         # Static assets (CSS, images)
│   ├── components/     # Reusable Vue components
│   ├── router/         # Vue Router configuration
│   ├── stores/         # Pinia stores
│   │   ├── auth.ts       # Authentication state
│   │   ├── search.ts     # Search state
│   │   ├── requests.ts   # User requests state
│   │   └── admin.ts      # Admin state
│   ├── services/       # API services
│   │   └── api.ts        # Axios client + API calls
│   ├── types/          # TypeScript types
│   │   └── api.ts        # API response types
│   ├── views/          # Page components
│   │   ├── Home.vue
│   │   ├── Login.vue
│   │   ├── Search.vue
│   │   ├── MyRequests.vue
│   │   └── Admin.vue
│   ├── App.vue         # Root component
│   └── main.ts         # Application entry point
├── index.html          # HTML template
├── vite.config.ts      # Vite configuration
├── tsconfig.json       # TypeScript configuration
├── package.json        # Dependencies
└── README.md           # This file
```

## Installation

```bash
cd frontend-v2
npm install
```

## Development

```bash
# Start dev server (http://localhost:5173)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Type checking
npm run type-check

# Lint
npm run lint

# Format
npm run format
```

## Features

### Authentication

- Login/logout
- JWT token management
- Auto-redirect on 401
- Protected routes (auth + admin)
- Persistent sessions (localStorage)

### State Management (Pinia)

**Auth Store** (`stores/auth.ts`):
- User authentication state
- Login/logout actions
- isAuthenticated/isAdmin getters

**Search Store** (`stores/search.ts`):
- Search results
- Media type filtering
- Search history

**Requests Store** (`stores/requests.ts`):
- User media requests
- Create/cancel requests
- Filter by status (pending, completed, failed)

**Admin Store** (`stores/admin.ts`):
- System statistics
- User management
- Settings management

### Routing

**Public routes**:
- `/` - Home page
- `/login` - Login page

**Protected routes** (requires auth):
- `/search` - Search media
- `/requests` - My requests

**Admin routes** (requires admin role):
- `/admin` - Admin dashboard

### API Client

Axios-based client with:
- Auto-injection of JWT token
- Auto-redirect on 401
- Error handling
- Type-safe endpoints

## API Integration

The frontend proxies `/api` requests to the backend during development (configured in `vite.config.ts`):

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8765',
      changeOrigin: true,
    }
  }
}
```

## Building for Production

```bash
npm run build
```

Builds to `../frontend/` directory (original frontend folder).

The build:
- Minifies JS/CSS
- Tree-shakes unused code
- Splits vendor chunks for caching
- Generates source maps (optional)

## CORS Configuration

The backend must allow the frontend origin in development:

**.env** (backend):
```bash
DEBUG=true
# Automatically allows localhost:5173
```

Or for production:
```bash
DEBUG=false
FRONTEND_URL=https://plex-kiosk.yourdomain.com
```

## Environment Variables

Create `.env.local` if needed:

```bash
# API URL (defaults to /api/v1)
VITE_API_BASE_URL=/api/v1
```

## Component Development

### Example Component

```vue
<template>
  <div class="my-component">
    <h1>{{ title }}</h1>
    <button @click="handleClick">Click me</button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Props {
  title: string
}

const props = defineProps<Props>()

const handleClick = () => {
  console.log('Clicked!')
}
</script>

<style scoped>
.my-component {
  padding: var(--spacing-lg);
}
</style>
```

## Component Migration Status (JOUR 11-13)

- [x] Common components (Navbar, LoadingSpinner, ErrorMessage, Modal)
- [x] Search components (MediaCard, MediaDetailsModal)
- [x] Request components (RequestCard, StatusBadge)
- [x] Admin components (StatsCard, UserTable, SettingsForm)
- [x] Views updated (Search, MyRequests, Admin, App)
- [x] Loading states + error handling implemented
- [x] Animations + transitions added
- [x] Responsive design implemented

## Next Steps (JOUR 14+)

- [ ] Backend/Frontend integration testing
- [ ] Build production bundle
- [ ] Add real-time updates (WebSocket - Phase 1+)
- [ ] User creation/edit modals (enhancement)
- [ ] Advanced filtering/sorting (enhancement)

## Troubleshooting

### Cannot connect to API

1. Check backend is running: `http://localhost:8765/api/health`
2. Check CORS configuration in backend
3. Check Vite proxy configuration

### Build fails

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

### Type errors

```bash
# Run type check
npm run type-check

# Update TypeScript if needed
npm install -D typescript@latest
```

## Resources

- [Vue.js 3 Docs](https://vuejs.org/)
- [Vite Docs](https://vitejs.dev/)
- [Pinia Docs](https://pinia.vuejs.org/)
- [Vue Router Docs](https://router.vuejs.org/)
- [TypeScript Docs](https://www.typescriptlang.org/)

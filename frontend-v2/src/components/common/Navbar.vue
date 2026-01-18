<template>
  <nav class="navbar">
    <div class="container navbar-content">
      <RouterLink to="/" class="logo">
        <h1>🎬 Plex Kiosk</h1>
      </RouterLink>

      <div v-if="authStore.isAuthenticated" class="nav-links">
        <RouterLink to="/search" class="nav-link">
          <span>🔍</span> Rechercher
        </RouterLink>
        <RouterLink to="/requests" class="nav-link">
          <span>📋</span> Mes demandes
        </RouterLink>
        <RouterLink v-if="authStore.isAdmin" to="/admin" class="nav-link">
          <span>⚙️</span> Admin
        </RouterLink>
      </div>

      <div class="user-menu">
        <div v-if="authStore.isAuthenticated" class="user-info">
          <span class="username">{{ authStore.user?.username }}</span>
          <button @click="handleLogout" class="btn btn-secondary btn-sm">
            Déconnexion
          </button>
        </div>
        <RouterLink v-else to="/login" class="btn btn-primary btn-sm">
          Connexion
        </RouterLink>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.navbar {
  background-color: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
  padding: var(--spacing-md) 0;
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(10px);
}

.navbar-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-xl);
}

.logo {
  text-decoration: none;
  color: var(--text-primary);
}

.logo h1 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
  color: var(--primary-color);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.nav-links {
  display: flex;
  gap: var(--spacing-lg);
  flex: 1;
}

.nav-link {
  text-decoration: none;
  color: var(--text-secondary);
  font-weight: 500;
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  transition: all var(--transition-normal);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.nav-link:hover,
.nav-link.router-link-active {
  color: var(--primary-color);
  background-color: rgba(229, 160, 13, 0.1);
}

.user-menu {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.username {
  color: var(--text-primary);
  font-weight: 500;
}

.btn-sm {
  padding: var(--spacing-xs) var(--spacing-md);
  font-size: 0.875rem;
}

@media (max-width: 768px) {
  .navbar-content {
    flex-wrap: wrap;
  }

  .nav-links {
    width: 100%;
    justify-content: center;
    order: 3;
  }
}
</style>

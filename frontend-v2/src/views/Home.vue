<template>
  <div class="home">
    <div class="container">
      <h1>Bienvenue sur Plex Kiosk</h1>
      <p class="subtitle">Votre système de kiosque self-service pour films, séries et animés</p>

      <div v-if="!authStore.isAuthenticated" class="cta-section">
        <RouterLink to="/login" class="btn btn-primary btn-large">
          Se connecter
        </RouterLink>
      </div>

      <div v-else class="user-section">
        <p>Connecté en tant que <strong>{{ authStore.user?.username }}</strong></p>
        <div class="actions">
          <RouterLink to="/search" class="btn btn-primary">
            Rechercher un média
          </RouterLink>
          <RouterLink to="/requests" class="btn btn-secondary">
            Mes demandes
          </RouterLink>
          <RouterLink v-if="authStore.isAdmin" to="/admin" class="btn btn-secondary">
            Administration
          </RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
</script>

<style scoped>
.home {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}

h1 {
  font-size: 3rem;
  margin-bottom: var(--spacing-md);
  color: var(--primary-color);
}

.subtitle {
  font-size: 1.25rem;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2xl);
}

.cta-section,
.user-section {
  margin-top: var(--spacing-2xl);
}

.actions {
  display: flex;
  gap: var(--spacing-md);
  justify-content: center;
  margin-top: var(--spacing-lg);
}

.btn-large {
  font-size: 1.25rem;
  padding: var(--spacing-md) var(--spacing-2xl);
}
</style>

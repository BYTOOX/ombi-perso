<template>
  <div class="login-page">
    <div class="login-card card">
      <h1>Connexion</h1>
      <p class="subtitle">Connectez-vous à votre compte</p>

      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="username">Nom d'utilisateur</label>
          <input
            id="username"
            v-model="username"
            type="text"
            class="input"
            placeholder="admin"
            required
            autocomplete="username"
          />
        </div>

        <div class="form-group">
          <label for="password">Mot de passe</label>
          <input
            id="password"
            v-model="password"
            type="password"
            class="input"
            placeholder="••••••••"
            required
            autocomplete="current-password"
          />
        </div>

        <div v-if="authStore.error" class="error-message">
          {{ authStore.error }}
        </div>

        <button type="submit" class="btn btn-primary btn-full" :disabled="authStore.loading">
          {{ authStore.loading ? 'Connexion...' : 'Se connecter' }}
        </button>
      </form>

      <p class="hint">
        Identifiants par défaut: <code>admin</code> / <code>admin</code>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')

async function handleLogin() {
  const success = await authStore.login(username.value, password.value)

  if (success) {
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-lg);
}

.login-card {
  width: 100%;
  max-width: 400px;
}

h1 {
  font-size: 2rem;
  margin-bottom: var(--spacing-sm);
  text-align: center;
  color: var(--primary-color);
}

.subtitle {
  text-align: center;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-xl);
}

.form-group {
  margin-bottom: var(--spacing-lg);
}

label {
  display: block;
  margin-bottom: var(--spacing-sm);
  font-weight: 500;
}

.btn-full {
  width: 100%;
  margin-top: var(--spacing-md);
}

.error-message {
  padding: var(--spacing-sm) var(--spacing-md);
  background-color: rgba(220, 38, 38, 0.1);
  border: 1px solid var(--error-color);
  border-radius: var(--radius-md);
  color: var(--error-color);
  margin-bottom: var(--spacing-md);
  text-align: center;
}

.hint {
  text-align: center;
  margin-top: var(--spacing-lg);
  color: var(--text-secondary);
  font-size: 0.875rem;
}

code {
  background-color: var(--bg-dark);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-family: 'Courier New', monospace;
  color: var(--primary-color);
}
</style>

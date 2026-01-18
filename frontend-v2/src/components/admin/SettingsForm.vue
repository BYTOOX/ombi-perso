<template>
  <div class="settings-form">
    <LoadingSpinner v-if="loading" message="Chargement des paramètres..." />

    <ErrorMessage
      v-else-if="error"
      :message="error"
      type="error"
      dismissible
      @dismiss="$emit('clear-error')"
    />

    <form v-else @submit.prevent="handleSubmit">
      <!-- Plex Settings -->
      <div class="settings-section">
        <h3 class="section-title">🎬 Plex</h3>
        <div class="form-grid">
          <div class="form-group">
            <label for="plex_url">URL Plex</label>
            <input
              id="plex_url"
              v-model="formData.plex_url"
              type="url"
              class="input"
              placeholder="http://localhost:32400"
              required
            />
          </div>

          <div class="form-group">
            <label for="plex_token">Token Plex</label>
            <input
              id="plex_token"
              v-model="formData.plex_token"
              type="password"
              class="input"
              placeholder="X-Plex-Token"
              required
            />
          </div>
        </div>
      </div>

      <!-- qBittorrent Settings -->
      <div class="settings-section">
        <h3 class="section-title">⬇️ qBittorrent</h3>
        <div class="form-grid">
          <div class="form-group">
            <label for="qbittorrent_url">URL qBittorrent</label>
            <input
              id="qbittorrent_url"
              v-model="formData.qbittorrent_url"
              type="url"
              class="input"
              placeholder="http://localhost:8080"
              required
            />
          </div>

          <div class="form-group">
            <label for="qbittorrent_username">Nom d'utilisateur</label>
            <input
              id="qbittorrent_username"
              v-model="formData.qbittorrent_username"
              type="text"
              class="input"
              placeholder="admin"
            />
          </div>

          <div class="form-group">
            <label for="qbittorrent_password">Mot de passe</label>
            <input
              id="qbittorrent_password"
              v-model="formData.qbittorrent_password"
              type="password"
              class="input"
              placeholder="••••••••"
            />
          </div>
        </div>
      </div>

      <!-- AI Settings -->
      <div class="settings-section">
        <h3 class="section-title">🤖 Intelligence Artificielle</h3>
        <div class="form-grid">
          <div class="form-group">
            <label for="ollama_url">URL Ollama</label>
            <input
              id="ollama_url"
              v-model="formData.ollama_url"
              type="url"
              class="input"
              placeholder="http://host.docker.internal:11434"
              required
            />
          </div>

          <div class="form-group">
            <label for="ollama_model">Modèle Ollama</label>
            <input
              id="ollama_model"
              v-model="formData.ollama_model"
              type="text"
              class="input"
              placeholder="llama3.2"
              required
            />
          </div>

          <div class="form-group form-group-full">
            <label>
              <input
                v-model="formData.ai_enabled"
                type="checkbox"
                class="checkbox"
              />
              Activer l'assistance IA
            </label>
          </div>
        </div>
      </div>

      <!-- Torrent Settings -->
      <div class="settings-section">
        <h3 class="section-title">🔍 Recherche de Torrents</h3>
        <div class="form-grid">
          <div class="form-group">
            <label for="flaresolverr_url">URL FlareSolverr</label>
            <input
              id="flaresolverr_url"
              v-model="formData.flaresolverr_url"
              type="url"
              class="input"
              placeholder="http://flaresolverr:8191"
            />
          </div>

          <div class="form-group">
            <label for="min_seeders">Seeders minimum</label>
            <input
              id="min_seeders"
              v-model.number="formData.min_seeders"
              type="number"
              class="input"
              min="0"
              placeholder="5"
            />
          </div>
        </div>
      </div>

      <!-- Notification Settings -->
      <div class="settings-section">
        <h3 class="section-title">🔔 Notifications</h3>
        <div class="form-grid">
          <div class="form-group">
            <label for="discord_webhook_url">Webhook Discord</label>
            <input
              id="discord_webhook_url"
              v-model="formData.discord_webhook_url"
              type="url"
              class="input"
              placeholder="https://discord.com/api/webhooks/..."
            />
          </div>

          <div class="form-group form-group-full">
            <label>
              <input
                v-model="formData.notifications_enabled"
                type="checkbox"
                class="checkbox"
              />
              Activer les notifications
            </label>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="form-actions">
        <button type="button" class="btn btn-secondary" @click="$emit('cancel')">
          Annuler
        </button>
        <button type="submit" class="btn btn-primary" :disabled="saving">
          {{ saving ? 'Enregistrement...' : 'Enregistrer' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

interface Settings {
  plex_url: string
  plex_token: string
  qbittorrent_url: string
  qbittorrent_username: string
  qbittorrent_password: string
  ollama_url: string
  ollama_model: string
  ai_enabled: boolean
  flaresolverr_url: string
  min_seeders: number
  discord_webhook_url: string
  notifications_enabled: boolean
}

interface Props {
  settings: Settings | null
  loading?: boolean
  saving?: boolean
  error?: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  submit: [settings: Settings]
  cancel: []
  'clear-error': []
}>()

const formData = ref<Settings>({
  plex_url: '',
  plex_token: '',
  qbittorrent_url: '',
  qbittorrent_username: '',
  qbittorrent_password: '',
  ollama_url: '',
  ollama_model: '',
  ai_enabled: false,
  flaresolverr_url: '',
  min_seeders: 5,
  discord_webhook_url: '',
  notifications_enabled: false,
})

watch(
  () => props.settings,
  (newSettings) => {
    if (newSettings) {
      formData.value = { ...newSettings }
    }
  },
  { immediate: true }
)

function handleSubmit() {
  emit('submit', formData.value)
}
</script>

<style scoped>
.settings-form {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: var(--spacing-xl);
}

.settings-section {
  margin-bottom: var(--spacing-2xl);
  padding-bottom: var(--spacing-xl);
  border-bottom: 1px solid var(--border-color);
}

.settings-section:last-of-type {
  border-bottom: none;
}

.section-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-lg);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--spacing-lg);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.form-group-full {
  grid-column: 1 / -1;
}

.form-group label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.input {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: 1rem;
  transition: all var(--transition-fast);
}

.input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(229, 160, 13, 0.1);
}

.checkbox {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--primary-color);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-md);
  margin-top: var(--spacing-xl);
  padding-top: var(--spacing-xl);
  border-top: 1px solid var(--border-color);
}

@media (max-width: 768px) {
  .settings-form {
    padding: var(--spacing-md);
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-actions {
    flex-direction: column;
  }

  .form-actions button {
    width: 100%;
  }
}
</style>

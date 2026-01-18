<template>
  <div class="admin-page">
    <div class="container">
      <h1>Administration</h1>
      <p class="subtitle">Gérez votre instance Plex Kiosk</p>

      <LoadingSpinner v-if="adminStore.loading" message="Chargement..." />

      <div v-else class="admin-content">
        <!-- Tabs -->
        <div class="tabs">
          <button
            @click="activeTab = 'dashboard'"
            :class="{ active: activeTab === 'dashboard' }"
            class="tab"
          >
            📊 Tableau de bord
          </button>
          <button
            @click="activeTab = 'users'"
            :class="{ active: activeTab === 'users' }"
            class="tab"
          >
            👥 Utilisateurs
          </button>
          <button
            @click="activeTab = 'settings'"
            :class="{ active: activeTab === 'settings' }"
            class="tab"
          >
            ⚙️ Paramètres
          </button>
        </div>

        <!-- Dashboard Tab -->
        <div v-show="activeTab === 'dashboard'" class="tab-content">
          <div v-if="adminStore.stats" class="stats-grid">
            <StatsCard
              label="Demandes totales"
              :value="adminStore.stats.total_requests"
              icon="📋"
              variant="info"
            />
            <StatsCard
              label="En attente"
              :value="adminStore.stats.pending_requests"
              icon="⏳"
              variant="warning"
            />
            <StatsCard
              label="Complétées"
              :value="adminStore.stats.completed_requests"
              icon="✅"
              variant="success"
            />
            <StatsCard
              label="Téléchargements actifs"
              :value="adminStore.stats.active_downloads"
              icon="⬇️"
              variant="primary"
            />
            <StatsCard
              label="Utilisateurs"
              :value="adminStore.stats.total_users"
              icon="👥"
              variant="info"
            />
            <StatsCard
              label="Éléments Plex"
              :value="adminStore.stats.plex_items"
              icon="🎬"
              variant="primary"
            />
          </div>
        </div>

        <!-- Users Tab -->
        <div v-show="activeTab === 'users'" class="tab-content">
          <UserTable
            :users="adminStore.users"
            :loading="adminStore.usersLoading"
            :error="adminStore.usersError"
            @create="handleCreateUser"
            @edit="handleEditUser"
            @delete="handleDeleteUser"
            @activate="handleActivateUser"
            @deactivate="handleDeactivateUser"
            @clear-error="adminStore.clearUsersError()"
          />
        </div>

        <!-- Settings Tab -->
        <div v-show="activeTab === 'settings'" class="tab-content">
          <SettingsForm
            :settings="adminStore.settings"
            :loading="adminStore.settingsLoading"
            :saving="adminStore.settingsSaving"
            :error="adminStore.settingsError"
            @submit="handleSaveSettings"
            @cancel="loadSettings"
            @clear-error="adminStore.clearSettingsError()"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAdminStore } from '@/stores/admin'
import StatsCard from '@/components/admin/StatsCard.vue'
import UserTable from '@/components/admin/UserTable.vue'
import SettingsForm from '@/components/admin/SettingsForm.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const adminStore = useAdminStore()
const activeTab = ref<'dashboard' | 'users' | 'settings'>('dashboard')

onMounted(() => {
  loadDashboard()
})

function loadDashboard() {
  adminStore.fetchStats()
}

function loadUsers() {
  adminStore.fetchUsers()
}

function loadSettings() {
  adminStore.fetchSettings()
}

// User management handlers
function handleCreateUser() {
  // TODO: Open user creation modal
  alert('Fonctionnalité de création d\'utilisateur à implémenter')
}

function handleEditUser(user: any) {
  // TODO: Open user edit modal
  alert(`Éditer utilisateur: ${user.username}`)
}

async function handleDeleteUser(user: any) {
  if (!confirm(`Êtes-vous sûr de vouloir supprimer l'utilisateur ${user.username} ?`)) {
    return
  }

  const success = await adminStore.deleteUser(user.id)
  if (success) {
    loadUsers()
  }
}

async function handleActivateUser(user: any) {
  const success = await adminStore.updateUserStatus(user.id, true)
  if (success) {
    loadUsers()
  }
}

async function handleDeactivateUser(user: any) {
  if (!confirm(`Êtes-vous sûr de vouloir désactiver ${user.username} ?`)) {
    return
  }

  const success = await adminStore.updateUserStatus(user.id, false)
  if (success) {
    loadUsers()
  }
}

// Settings handlers
async function handleSaveSettings(settings: any) {
  const success = await adminStore.updateSettings(settings)
  if (success) {
    alert('Paramètres sauvegardés avec succès')
  }
}

// Load data when switching tabs
function handleTabChange(tab: 'dashboard' | 'users' | 'settings') {
  activeTab.value = tab

  if (tab === 'users' && adminStore.users.length === 0) {
    loadUsers()
  } else if (tab === 'settings' && !adminStore.settings) {
    loadSettings()
  }
}
</script>

<style scoped>
.admin-page {
  padding: var(--spacing-2xl) 0;
  min-height: calc(100vh - 80px);
}

h1 {
  font-size: 2.5rem;
  margin-bottom: var(--spacing-sm);
  color: var(--primary-color);
}

.subtitle {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2xl);
  font-size: 1.125rem;
}

.admin-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.tabs {
  display: flex;
  gap: var(--spacing-sm);
  border-bottom: 2px solid var(--border-color);
  overflow-x: auto;
}

.tab {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 1rem;
  font-weight: 500;
  padding: var(--spacing-md) var(--spacing-lg);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all var(--transition-fast);
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.tab:hover {
  color: var(--text-primary);
}

.tab.active {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
}

.tab-content {
  animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-xl);
}

@media (max-width: 768px) {
  .admin-page {
    padding: var(--spacing-lg) 0;
  }

  h1 {
    font-size: 2rem;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .tabs {
    gap: var(--spacing-xs);
  }

  .tab {
    padding: var(--spacing-sm) var(--spacing-md);
    font-size: 0.875rem;
  }
}
</style>

<template>
  <div class="user-table-container">
    <div class="table-header">
      <h2>Utilisateurs</h2>
      <button class="btn btn-primary" @click="$emit('create')">
        ➕ Nouvel utilisateur
      </button>
    </div>

    <LoadingSpinner v-if="loading" message="Chargement des utilisateurs..." />

    <ErrorMessage
      v-else-if="error"
      :message="error"
      type="error"
      dismissible
      @dismiss="$emit('clear-error')"
    />

    <div v-else-if="users.length === 0" class="empty-state">
      <p>Aucun utilisateur trouvé</p>
    </div>

    <div v-else class="table-wrapper">
      <table class="user-table">
        <thead>
          <tr>
            <th>Utilisateur</th>
            <th>Email</th>
            <th>Rôle</th>
            <th>Statut</th>
            <th>Demandes</th>
            <th>Créé le</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id" :class="{ inactive: !user.is_active }">
            <td>
              <div class="user-info">
                <div class="user-avatar">{{ user.username.charAt(0).toUpperCase() }}</div>
                <div class="user-details">
                  <div class="user-name">{{ user.username }}</div>
                  <div v-if="!user.is_active" class="user-inactive">Inactif</div>
                </div>
              </div>
            </td>
            <td>{{ user.email }}</td>
            <td>
              <span class="role-badge" :class="`role-${user.role}`">
                {{ getRoleLabel(user.role) }}
              </span>
            </td>
            <td>
              <span class="status-badge" :class="`status-${user.status}`">
                {{ getStatusLabel(user.status) }}
              </span>
            </td>
            <td class="text-center">{{ user.request_count || 0 }}</td>
            <td>{{ formatDate(user.created_at) }}</td>
            <td>
              <div class="actions">
                <button
                  class="btn-icon"
                  @click="$emit('edit', user)"
                  title="Modifier"
                >
                  ✏️
                </button>
                <button
                  v-if="user.is_active"
                  class="btn-icon btn-warning"
                  @click="$emit('deactivate', user)"
                  title="Désactiver"
                >
                  🚫
                </button>
                <button
                  v-else
                  class="btn-icon btn-success"
                  @click="$emit('activate', user)"
                  title="Activer"
                >
                  ✅
                </button>
                <button
                  class="btn-icon btn-danger"
                  @click="$emit('delete', user)"
                  title="Supprimer"
                  :disabled="user.role === 'admin'"
                >
                  🗑️
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

interface User {
  id: number
  username: string
  email: string
  role: string
  status: string
  is_active: boolean
  request_count?: number
  created_at: string
}

interface Props {
  users: User[]
  loading?: boolean
  error?: string | null
}

defineProps<Props>()

defineEmits<{
  create: []
  edit: [user: User]
  delete: [user: User]
  activate: [user: User]
  deactivate: [user: User]
  'clear-error': []
}>()

function getRoleLabel(role: string): string {
  const labels: Record<string, string> = {
    admin: 'Admin',
    user: 'Utilisateur',
    moderator: 'Modérateur',
  }
  return labels[role] || role
}

function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: 'Actif',
    pending: 'En attente',
    suspended: 'Suspendu',
    banned: 'Banni',
  }
  return labels[status] || status
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return new Intl.DateTimeFormat('fr-FR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date)
}
</script>

<style scoped>
.user-table-container {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: var(--spacing-xl);
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xl);
}

.table-header h2 {
  font-size: 1.5rem;
  color: var(--text-primary);
}

.table-wrapper {
  overflow-x: auto;
}

.user-table {
  width: 100%;
  border-collapse: collapse;
}

.user-table thead {
  background: rgba(229, 160, 13, 0.1);
}

.user-table th {
  text-align: left;
  padding: var(--spacing-md);
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 2px solid var(--border-color);
}

.user-table td {
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--border-color);
}

.user-table tbody tr {
  transition: background-color var(--transition-fast);
}

.user-table tbody tr:hover {
  background: rgba(229, 160, 13, 0.05);
}

.user-table tbody tr.inactive {
  opacity: 0.6;
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.user-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--primary-color);
  color: #000;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1.125rem;
}

.user-details {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.user-name {
  font-weight: 600;
  color: var(--text-primary);
}

.user-inactive {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.role-badge,
.status-badge {
  display: inline-block;
  padding: 4px var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.role-admin {
  background: rgba(220, 38, 38, 0.15);
  color: var(--error-color);
}

.role-moderator {
  background: rgba(229, 160, 13, 0.15);
  color: var(--primary-color);
}

.role-user {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.status-active {
  background: rgba(22, 163, 74, 0.15);
  color: var(--success-color);
}

.status-pending {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning-color);
}

.status-suspended,
.status-banned {
  background: rgba(220, 38, 38, 0.15);
  color: var(--error-color);
}

.text-center {
  text-align: center;
}

.actions {
  display: flex;
  gap: var(--spacing-xs);
}

.btn-icon {
  background: none;
  border: none;
  font-size: 1.125rem;
  cursor: pointer;
  padding: var(--spacing-xs);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  opacity: 0.7;
}

.btn-icon:hover:not(:disabled) {
  opacity: 1;
  background: rgba(229, 160, 13, 0.1);
}

.btn-icon:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-icon.btn-warning:hover:not(:disabled) {
  background: rgba(245, 158, 11, 0.1);
}

.btn-icon.btn-success:hover:not(:disabled) {
  background: rgba(22, 163, 74, 0.1);
}

.btn-icon.btn-danger:hover:not(:disabled) {
  background: rgba(220, 38, 38, 0.1);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-2xl);
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .user-table-container {
    padding: var(--spacing-md);
  }

  .table-header {
    flex-direction: column;
    gap: var(--spacing-md);
    align-items: flex-start;
  }

  .user-table {
    font-size: 0.875rem;
  }

  .user-table th,
  .user-table td {
    padding: var(--spacing-sm);
  }

  .user-avatar {
    width: 32px;
    height: 32px;
    font-size: 0.875rem;
  }
}
</style>

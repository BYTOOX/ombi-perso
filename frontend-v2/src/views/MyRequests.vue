<template>
  <div class="requests-page">
    <div class="container">
      <h1>Mes demandes</h1>
      <p class="subtitle">Suivez l'état de vos demandes de médias</p>

      <LoadingSpinner v-if="requestsStore.loading" message="Chargement des demandes..." />

      <ErrorMessage
        v-else-if="requestsStore.error"
        :message="requestsStore.error"
        type="error"
        dismissible
        @dismiss="requestsStore.clearError()"
      />

      <div v-else-if="requestsStore.requests.length === 0" class="empty-state">
        <div class="empty-icon">📋</div>
        <h2>Aucune demande</h2>
        <p>Vous n'avez pas encore fait de demandes</p>
        <RouterLink to="/search" class="btn btn-primary">
          🔍 Rechercher un média
        </RouterLink>
      </div>

      <div v-else class="requests-container">
        <!-- Filter tabs -->
        <div class="tabs">
          <button
            @click="activeTab = 'all'"
            :class="{ active: activeTab === 'all' }"
            class="tab"
          >
            Toutes ({{ requestsStore.requests.length }})
          </button>
          <button
            @click="activeTab = 'pending'"
            :class="{ active: activeTab === 'pending' }"
            class="tab"
          >
            En cours ({{ requestsStore.pendingRequests.length }})
          </button>
          <button
            @click="activeTab = 'completed'"
            :class="{ active: activeTab === 'completed' }"
            class="tab"
          >
            Complétées ({{ requestsStore.completedRequests.length }})
          </button>
          <button
            @click="activeTab = 'failed'"
            :class="{ active: activeTab === 'failed' }"
            class="tab"
          >
            Échouées ({{ requestsStore.failedRequests.length }})
          </button>
        </div>

        <!-- Requests list -->
        <div class="requests-list">
          <RequestCard
            v-for="request in filteredRequests"
            :key="request.id"
            :request="request"
            @cancel="handleCancelRequest"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useRequestsStore } from '@/stores/requests'
import RequestCard from '@/components/requests/RequestCard.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const requestsStore = useRequestsStore()
const activeTab = ref<'all' | 'pending' | 'completed' | 'failed'>('all')

const filteredRequests = computed(() => {
  switch (activeTab.value) {
    case 'pending':
      return requestsStore.pendingRequests
    case 'completed':
      return requestsStore.completedRequests
    case 'failed':
      return requestsStore.failedRequests
    default:
      return requestsStore.requests
  }
})

onMounted(() => {
  requestsStore.fetchMyRequests()

  // Auto-refresh every 30 seconds
  const interval = setInterval(() => {
    requestsStore.fetchMyRequests()
  }, 30000)

  // Cleanup
  onBeforeUnmount(() => {
    clearInterval(interval)
  })
})

import { onBeforeUnmount } from 'vue'

async function handleCancelRequest(id: number) {
  if (!confirm('Êtes-vous sûr de vouloir annuler cette demande ?')) return

  const success = await requestsStore.cancelRequest(id)
  if (!success) {
    alert('Erreur lors de l\'annulation de la demande')
  }
}
</script>

<style scoped>
.requests-page {
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

.empty-state {
  text-align: center;
  padding: var(--spacing-2xl);
  max-width: 500px;
  margin: 0 auto;
}

.empty-icon {
  font-size: 4rem;
  margin-bottom: var(--spacing-lg);
}

.empty-state h2 {
  font-size: 1.5rem;
  margin-bottom: var(--spacing-sm);
  color: var(--text-primary);
}

.empty-state p {
  margin-bottom: var(--spacing-xl);
  color: var(--text-secondary);
}

.requests-container {
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
  font-size: 0.875rem;
  font-weight: 500;
  padding: var(--spacing-md) var(--spacing-lg);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.tab:hover {
  color: var(--text-primary);
}

.tab.active {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
}

.requests-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}
</style>

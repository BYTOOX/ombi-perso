<template>
  <div class="search-page">
    <div class="container">
      <h1>Rechercher un média</h1>
      <p class="subtitle">Films, séries, animés...</p>

      <div class="search-bar">
        <input
          v-model="searchQuery"
          type="text"
          class="input search-input"
          placeholder="Rechercher un titre..."
          @keyup.enter="handleSearch"
          autofocus
        />
        <button class="btn btn-primary" @click="handleSearch" :disabled="searchStore.loading">
          {{ searchStore.loading ? 'Recherche...' : '🔍 Rechercher' }}
        </button>
      </div>

      <ErrorMessage
        v-if="searchStore.error"
        :message="searchStore.error"
        type="error"
        dismissible
        @dismiss="searchStore.clearResults()"
      />

      <LoadingSpinner v-if="searchStore.loading" message="Recherche en cours..." />

      <div v-else-if="searchStore.results.length > 0" class="results">
        <p class="results-count">
          {{ searchStore.results.length }} résultat{{ searchStore.results.length > 1 ? 's' : '' }}
          trouvé{{ searchStore.results.length > 1 ? 's' : '' }}
        </p>

        <div class="results-grid">
          <MediaCard
            v-for="result in searchStore.results"
            :key="result.id"
            :media="result"
            @select="handleSelectMedia"
          />
        </div>
      </div>

      <div v-else-if="searchQuery && !searchStore.loading" class="empty-state">
        <p>Aucun résultat trouvé</p>
      </div>
    </div>

    <!-- Media Details Modal -->
    <MediaDetailsModal
      v-model="showDetailsModal"
      :media="selectedMedia"
      @close="showDetailsModal = false"
      @success="handleRequestSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useSearchStore } from '@/stores/search'
import MediaCard from '@/components/search/MediaCard.vue'
import MediaDetailsModal from '@/components/search/MediaDetailsModal.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import type { SearchResult } from '@/types/api'

const router = useRouter()
const searchStore = useSearchStore()

const searchQuery = ref(searchStore.lastQuery || '')
const selectedMedia = ref<SearchResult | null>(null)
const showDetailsModal = ref(false)

function handleSearch() {
  if (!searchQuery.value.trim()) return
  searchStore.search(searchQuery.value)
}

function handleSelectMedia(media: SearchResult) {
  selectedMedia.value = media
  showDetailsModal.value = true
}

function handleRequestSuccess() {
  // Redirect to requests page after successful request
  router.push('/requests')
}
</script>

<style scoped>
.search-page {
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

.search-bar {
  display: flex;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-xl);
}

.search-input {
  flex: 1;
  font-size: 1.125rem;
}

.results-count {
  margin-bottom: var(--spacing-xl);
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--spacing-lg);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-2xl);
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .search-bar {
    flex-direction: column;
  }

  .results-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: var(--spacing-md);
  }
}
</style>

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/services/api'
import type { SearchResult } from '@/types/api'

export const useSearchStore = defineStore('search', () => {
  // State
  const results = ref<SearchResult[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastQuery = ref('')
  const selectedMediaType = ref('all')

  // Actions
  async function search(query: string, mediaType: string = 'all') {
    if (!query.trim()) {
      results.value = []
      return
    }

    loading.value = true
    error.value = null
    lastQuery.value = query
    selectedMediaType.value = mediaType

    try {
      results.value = await api.searchMedia(query, mediaType)
    } catch (err: any) {
      error.value = err.message || 'Erreur de recherche'
      results.value = []
    } finally {
      loading.value = false
    }
  }

  function clearResults() {
    results.value = []
    lastQuery.value = ''
    error.value = null
  }

  return {
    // State
    results,
    loading,
    error,
    lastQuery,
    selectedMediaType,
    // Actions
    search,
    clearResults,
  }
})

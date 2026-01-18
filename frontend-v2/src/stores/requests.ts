import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/services/api'
import type { MediaRequest } from '@/types/api'

export const useRequestsStore = defineStore('requests', () => {
  // State
  const requests = ref<MediaRequest[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const pendingRequests = computed(() =>
    requests.value.filter(r => ['pending', 'searching', 'downloading', 'processing'].includes(r.status))
  )

  const completedRequests = computed(() =>
    requests.value.filter(r => r.status === 'completed')
  )

  const failedRequests = computed(() =>
    requests.value.filter(r => r.status === 'error')
  )

  // Actions
  async function fetchMyRequests() {
    loading.value = true
    error.value = null

    try {
      requests.value = await api.getMyRequests()
    } catch (err: any) {
      error.value = err.message || 'Erreur de chargement des requêtes'
    } finally {
      loading.value = false
    }
  }

  async function fetchAllRequests() {
    loading.value = true
    error.value = null

    try {
      requests.value = await api.getAllRequests()
    } catch (err: any) {
      error.value = err.message || 'Erreur de chargement des requêtes'
    } finally {
      loading.value = false
    }
  }

  async function createRequest(data: {
    media_type: string
    external_id: string
    source: string
    title: string
    original_title?: string
    year?: number
    poster_url?: string
    overview?: string
    quality_preference?: string
    seasons_requested?: string
  }): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const newRequest = await api.createRequest(data)
      requests.value.unshift(newRequest)
      return true
    } catch (err: any) {
      error.value = err.message || 'Erreur de création de la requête'
      return false
    } finally {
      loading.value = false
    }
  }

  async function cancelRequest(id: number): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      await api.cancelRequest(id)
      requests.value = requests.value.filter(r => r.id !== id)
      return true
    } catch (err: any) {
      error.value = err.message || 'Erreur d\'annulation de la requête'
      return false
    } finally {
      loading.value = false
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    requests,
    loading,
    error,
    // Getters
    pendingRequests,
    completedRequests,
    failedRequests,
    // Actions
    fetchMyRequests,
    fetchAllRequests,
    createRequest,
    cancelRequest,
    clearError,
  }
})

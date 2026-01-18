import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/services/api'
import type { Stats } from '@/types/api'

export const useAdminStore = defineStore('admin', () => {
  // State
  const stats = ref<Stats | null>(null)
  const users = ref<any[]>([])
  const settings = ref<any>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Separate loading/error states for each section
  const usersLoading = ref(false)
  const usersError = ref<string | null>(null)
  const settingsLoading = ref(false)
  const settingsSaving = ref(false)
  const settingsError = ref<string | null>(null)

  // Actions
  async function fetchStats() {
    loading.value = true
    error.value = null

    try {
      stats.value = await api.getStats()
    } catch (err: any) {
      error.value = err.message || 'Erreur de chargement des statistiques'
    } finally {
      loading.value = false
    }
  }

  async function fetchUsers() {
    usersLoading.value = true
    usersError.value = null

    try {
      users.value = await api.getUsers()
    } catch (err: any) {
      usersError.value = err.message || 'Erreur de chargement des utilisateurs'
    } finally {
      usersLoading.value = false
    }
  }

  async function deleteUser(userId: number): Promise<boolean> {
    usersLoading.value = true
    usersError.value = null

    try {
      await api.deleteUser(userId)
      users.value = users.value.filter((u) => u.id !== userId)
      return true
    } catch (err: any) {
      usersError.value = err.message || 'Erreur de suppression de l\'utilisateur'
      return false
    } finally {
      usersLoading.value = false
    }
  }

  async function updateUserStatus(userId: number, isActive: boolean): Promise<boolean> {
    usersLoading.value = true
    usersError.value = null

    try {
      await api.updateUserStatus(userId, isActive)
      const user = users.value.find((u) => u.id === userId)
      if (user) {
        user.is_active = isActive
      }
      return true
    } catch (err: any) {
      usersError.value = err.message || 'Erreur de mise à jour du statut'
      return false
    } finally {
      usersLoading.value = false
    }
  }

  async function fetchSettings() {
    settingsLoading.value = true
    settingsError.value = null

    try {
      settings.value = await api.getSettings()
    } catch (err: any) {
      settingsError.value = err.message || 'Erreur de chargement des paramètres'
    } finally {
      settingsLoading.value = false
    }
  }

  async function updateSettings(newSettings: any): Promise<boolean> {
    settingsSaving.value = true
    settingsError.value = null

    try {
      settings.value = await api.updateSettings(newSettings)
      return true
    } catch (err: any) {
      settingsError.value = err.message || 'Erreur de mise à jour des paramètres'
      return false
    } finally {
      settingsSaving.value = false
    }
  }

  function clearError() {
    error.value = null
  }

  function clearUsersError() {
    usersError.value = null
  }

  function clearSettingsError() {
    settingsError.value = null
  }

  return {
    // State
    stats,
    users,
    settings,
    loading,
    error,
    usersLoading,
    usersError,
    settingsLoading,
    settingsSaving,
    settingsError,
    // Actions
    fetchStats,
    fetchUsers,
    deleteUser,
    updateUserStatus,
    fetchSettings,
    updateSettings,
    clearError,
    clearUsersError,
    clearSettingsError,
  }
})

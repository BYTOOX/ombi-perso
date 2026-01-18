import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/services/api'
import type { User } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  // State
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  // Actions
  async function login(username: string, password: string) {
    loading.value = true
    error.value = null

    try {
      const data = await api.login(username, password)

      token.value = data.access_token
      user.value = data.user

      localStorage.setItem('token', data.access_token)

      return true
    } catch (err: any) {
      error.value = err.message || 'Erreur de connexion'
      return false
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    loading.value = true

    try {
      await api.logout()
    } catch (err) {
      // Ignore logout errors
    } finally {
      token.value = null
      user.value = null
      localStorage.removeItem('token')
      loading.value = false
    }
  }

  async function fetchCurrentUser() {
    if (!token.value) return

    loading.value = true
    error.value = null

    try {
      user.value = await api.getCurrentUser()
    } catch (err: any) {
      error.value = err.message
      // If fetch fails, clear token
      token.value = null
      user.value = null
      localStorage.removeItem('token')
    } finally {
      loading.value = false
    }
  }

  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('token', newToken)
    fetchCurrentUser()
  }

  return {
    // State
    token,
    user,
    loading,
    error,
    // Getters
    isAuthenticated,
    isAdmin,
    // Actions
    login,
    logout,
    fetchCurrentUser,
    setToken,
  }
})

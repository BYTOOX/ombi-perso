import axios, { type AxiosInstance, type AxiosError } from 'axios'
import type {
  LoginResponse,
  MediaRequest,
  SearchResult,
  PlexLibraryItem,
  Stats,
  ApiError,
} from '@/types/api'

class ApiService {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: '/api/v1',
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Request interceptor - Add auth token
    this.client.interceptors.request.use(
      config => {
        const token = localStorage.getItem('token')
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      error => Promise.reject(error)
    )

    // Response interceptor - Handle errors
    this.client.interceptors.response.use(
      response => response,
      (error: AxiosError<ApiError>) => {
        // Handle 401 Unauthorized - logout user
        if (error.response?.status === 401) {
          localStorage.removeItem('token')
          window.location.href = '/login'
        }

        // Extract error message
        const message =
          typeof error.response?.data?.detail === 'string'
            ? error.response.data.detail
            : 'Une erreur est survenue'

        return Promise.reject(new Error(message))
      }
    )
  }

  // =============================================================================
  // AUTH
  // =============================================================================

  async login(username: string, password: string): Promise<LoginResponse> {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)

    const response = await this.client.post<LoginResponse>('/auth/login', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  }

  async logout(): Promise<void> {
    await this.client.post('/auth/logout')
  }

  async getCurrentUser() {
    const response = await this.client.get('/auth/me')
    return response.data
  }

  // =============================================================================
  // SEARCH
  // =============================================================================

  async searchMedia(query: string, mediaType: string = 'all'): Promise<SearchResult[]> {
    const response = await this.client.get<SearchResult[]>('/search/', {
      params: { query, type: mediaType },
    })
    return response.data
  }

  // =============================================================================
  // REQUESTS
  // =============================================================================

  async createRequest(data: {
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
  }): Promise<MediaRequest> {
    const response = await this.client.post<MediaRequest>('/requests', data)
    return response.data
  }

  async getMyRequests(): Promise<MediaRequest[]> {
    const response = await this.client.get<MediaRequest[]>('/requests/my')
    return response.data
  }

  async getAllRequests(): Promise<MediaRequest[]> {
    const response = await this.client.get<MediaRequest[]>('/requests')
    return response.data
  }

  async getRequest(id: number): Promise<MediaRequest> {
    const response = await this.client.get<MediaRequest>(`/requests/${id}`)
    return response.data
  }

  async cancelRequest(id: number): Promise<MediaRequest> {
    const response = await this.client.delete<MediaRequest>(`/requests/${id}`)
    return response.data
  }

  // =============================================================================
  // PLEX
  // =============================================================================

  async getPlexLibrary(
    mediaType?: string,
    limit: number = 50,
    offset: number = 0
  ): Promise<PlexLibraryItem[]> {
    const response = await this.client.get<PlexLibraryItem[]>('/plex/library', {
      params: { media_type: mediaType, limit, offset },
    })
    return response.data
  }

  async searchPlexLibrary(query: string): Promise<PlexLibraryItem[]> {
    const response = await this.client.get<PlexLibraryItem[]>('/plex/search', {
      params: { query },
    })
    return response.data
  }

  async syncPlexLibrary(fullSync: boolean = false): Promise<any> {
    const response = await this.client.post('/plex/sync', { full_sync: fullSync })
    return response.data
  }

  // =============================================================================
  // ADMIN
  // =============================================================================

  async getStats(): Promise<Stats> {
    const response = await this.client.get<Stats>('/admin/stats')
    return response.data
  }

  async getUsers(): Promise<any[]> {
    const response = await this.client.get('/admin/users')
    return response.data
  }

  async deleteUser(userId: number): Promise<void> {
    await this.client.delete(`/admin/users/${userId}`)
  }

  async updateUserStatus(userId: number, isActive: boolean): Promise<void> {
    await this.client.patch(`/admin/users/${userId}`, { is_active: isActive })
  }

  async getSettings(): Promise<any> {
    const response = await this.client.get('/admin/settings')
    return response.data
  }

  async updateSettings(settings: any): Promise<any> {
    const response = await this.client.put('/admin/settings', settings)
    return response.data
  }
}

// Export singleton instance
export const api = new ApiService()

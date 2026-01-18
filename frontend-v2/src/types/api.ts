/**
 * API Response Types
 */

export interface User {
  id: number
  username: string
  email: string
  role: 'admin' | 'user'
  status: string
  is_active: boolean
  created_at: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface MediaRequest {
  id: number
  user_id: number
  username?: string
  media_type: 'movie' | 'animated_movie' | 'series' | 'animated_series' | 'anime'
  external_id: string
  source: string
  title: string
  original_title?: string
  year?: number
  poster_url?: string
  overview?: string
  quality_preference: string
  seasons_requested?: string
  status: RequestStatus
  status_message?: string
  celery_task_id?: string
  created_at: string
  updated_at: string
  completed_at?: string
}

export type RequestStatus =
  | 'pending'
  | 'searching'
  | 'awaiting_approval'
  | 'downloading'
  | 'processing'
  | 'completed'
  | 'error'
  | 'cancelled'

export interface SearchResult {
  id: string
  title: string
  original_title?: string
  year?: number
  media_type: string
  poster_url?: string
  overview?: string
  vote_average?: number
  source: 'tmdb' | 'anilist'
}

export interface PlexLibraryItem {
  id: number
  plex_key: string
  title: string
  media_type: string
  year?: number
  poster_url?: string
  library_section?: string
  added_at?: string
}

export interface Stats {
  total_requests: number
  pending_requests: number
  completed_requests: number
  active_downloads: number
  total_users: number
  plex_items: number
}

export interface ApiError {
  detail: string | Record<string, any>
}

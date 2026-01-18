<template>
  <div class="media-card" @click="$emit('select', media)">
    <div class="poster">
      <img v-if="media.poster_url" :src="media.poster_url" :alt="media.title" loading="lazy" />
      <div v-else class="poster-placeholder">
        <span>{{ mediaTypeIcon }}</span>
      </div>
      <div class="overlay">
        <button class="request-btn btn btn-primary btn-sm">
          + Demander
        </button>
      </div>
    </div>

    <div class="info">
      <h3 class="title" :title="media.title">{{ media.title }}</h3>
      <p class="year">{{ media.year || 'N/A' }}</p>

      <div class="meta">
        <span class="type-badge">{{ mediaTypeLabel }}</span>
        <span v-if="media.vote_average" class="rating">
          ⭐ {{ media.vote_average?.toFixed(1) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SearchResult } from '@/types/api'

interface Props {
  media: SearchResult
}

const props = defineProps<Props>()

defineEmits<{
  select: [media: SearchResult]
}>()

const mediaTypeIcon = computed(() => {
  switch (props.media.media_type) {
    case 'movie':
      return '🎬'
    case 'animated_movie':
      return '🎨'
    case 'series':
      return '📺'
    case 'animated_series':
      return '🎞️'
    case 'anime':
      return '🇯🇵'
    default:
      return '📽️'
  }
})

const mediaTypeLabel = computed(() => {
  switch (props.media.media_type) {
    case 'movie':
      return 'Film'
    case 'animated_movie':
      return 'Film animé'
    case 'series':
      return 'Série'
    case 'animated_series':
      return 'Série animée'
    case 'anime':
      return 'Anime'
    default:
      return props.media.media_type
  }
})
</script>

<style scoped>
.media-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--transition-normal);
}

.media-card:hover {
  transform: translateY(-4px);
  border-color: var(--primary-color);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.3);
}

.poster {
  position: relative;
  aspect-ratio: 2 / 3;
  overflow: hidden;
  background-color: var(--bg-dark);
}

.poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--transition-slow);
}

.media-card:hover .poster img {
  transform: scale(1.05);
}

.poster-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 4rem;
}

.overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.9), transparent);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: var(--spacing-md);
  opacity: 0;
  transition: opacity var(--transition-normal);
}

.media-card:hover .overlay {
  opacity: 1;
}

.request-btn {
  white-space: nowrap;
}

.info {
  padding: var(--spacing-md);
}

.title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 var(--spacing-xs) 0;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.year {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-sm) 0;
}

.meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.type-badge {
  background-color: var(--bg-dark);
  color: var(--primary-color);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.rating {
  font-size: 0.875rem;
  color: var(--text-secondary);
}
</style>

<template>
  <div class="request-card card">
    <div class="request-content">
      <div class="poster-thumb">
        <img v-if="request.poster_url" :src="request.poster_url" :alt="request.title" />
        <div v-else class="poster-placeholder">📽️</div>
      </div>

      <div class="request-info">
        <div class="header">
          <h3>{{ request.title }}</h3>
          <StatusBadge :status="request.status" />
        </div>

        <div class="meta">
          <span v-if="request.year" class="meta-item">{{ request.year }}</span>
          <span class="meta-item">{{ mediaTypeLabel }}</span>
          <span class="meta-item">{{ requestQuality }}</span>
        </div>

        <p v-if="request.status_message" class="status-message">
          {{ request.status_message }}
        </p>

        <div class="timestamps">
          <span>Demandé le {{ formatDate(request.created_at) }}</span>
          <span v-if="request.completed_at">
            • Complété le {{ formatDate(request.completed_at) }}
          </span>
        </div>

        <div v-if="showProgress" class="progress-bar">
          <div class="progress-fill" :style="{ width: `${progress}%` }"></div>
        </div>
      </div>

      <div class="actions">
        <button
          v-if="canCancel"
          @click="$emit('cancel', request.id)"
          class="btn btn-secondary btn-sm"
          title="Annuler la demande"
        >
          ✕
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusBadge from './StatusBadge.vue'
import type { MediaRequest } from '@/types/api'

interface Props {
  request: MediaRequest
}

const props = defineProps<Props>()

defineEmits<{
  cancel: [id: number]
}>()

const mediaTypeLabel = computed(() => {
  switch (props.request.media_type) {
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
      return props.request.media_type
  }
})

const requestQuality = computed(() => props.request.quality_preference || '1080p')

const canCancel = computed(() =>
  ['pending', 'searching', 'awaiting_approval'].includes(props.request.status)
)

const showProgress = computed(() =>
  ['downloading', 'processing'].includes(props.request.status)
)

const progress = computed(() => {
  if (props.request.status === 'downloading') return 60
  if (props.request.status === 'processing') return 90
  return 0
})

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.request-card {
  padding: var(--spacing-lg);
  transition: all var(--transition-normal);
}

.request-card:hover {
  border-color: var(--primary-color);
}

.request-content {
  display: grid;
  grid-template-columns: 80px 1fr auto;
  gap: var(--spacing-lg);
  align-items: start;
}

.poster-thumb {
  width: 80px;
  aspect-ratio: 2 / 3;
  border-radius: var(--radius-md);
  overflow: hidden;
  background-color: var(--bg-dark);
}

.poster-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.poster-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
}

.request-info {
  flex: 1;
  min-width: 0;
}

.header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
  flex-wrap: wrap;
}

.header h3 {
  margin: 0;
  font-size: 1.125rem;
  color: var(--text-primary);
}

.meta {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
  flex-wrap: wrap;
}

.meta-item {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.meta-item:not(:last-child)::after {
  content: '•';
  margin-left: var(--spacing-sm);
  color: var(--border-color);
}

.status-message {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: var(--spacing-sm) 0;
  font-style: italic;
}

.timestamps {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-top: var(--spacing-sm);
}

.progress-bar {
  width: 100%;
  height: 4px;
  background-color: var(--bg-dark);
  border-radius: 2px;
  overflow: hidden;
  margin-top: var(--spacing-md);
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary-color), var(--secondary-color));
  transition: width var(--transition-slow);
}

.actions {
  display: flex;
  gap: var(--spacing-sm);
}

@media (max-width: 768px) {
  .request-content {
    grid-template-columns: 60px 1fr;
  }

  .poster-thumb {
    width: 60px;
  }

  .actions {
    grid-column: 2;
    justify-content: flex-end;
  }
}
</style>

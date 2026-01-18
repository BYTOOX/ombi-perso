<template>
  <Modal v-model="isOpen" :title="media?.title || ''" @close="$emit('close')">
    <div v-if="media" class="media-details">
      <div class="details-content">
        <div class="poster-section">
          <img v-if="media.poster_url" :src="media.poster_url" :alt="media.title" />
          <div v-else class="poster-placeholder">📽️</div>
        </div>

        <div class="info-section">
          <h3>{{ media.title }}</h3>
          <p v-if="media.original_title && media.original_title !== media.title" class="original-title">
            Titre original: {{ media.original_title }}
          </p>

          <div class="meta-info">
            <span class="meta-item">
              <strong>Année:</strong> {{ media.year || 'N/A' }}
            </span>
            <span class="meta-item">
              <strong>Type:</strong> {{ mediaTypeLabel }}
            </span>
            <span v-if="media.vote_average" class="meta-item">
              <strong>Note:</strong> ⭐ {{ media.vote_average.toFixed(1) }}/10
            </span>
          </div>

          <p v-if="media.overview" class="overview">{{ media.overview }}</p>
          <p v-else class="overview empty">Aucun résumé disponible</p>

          <div class="request-form">
            <label for="quality">Qualité préférée:</label>
            <select id="quality" v-model="requestQuality" class="input">
              <option value="720p">720p</option>
              <option value="1080p">1080p (recommandé)</option>
              <option value="2160p">4K (2160p)</option>
            </select>

            <button
              @click="handleRequest"
              class="btn btn-primary btn-full"
              :disabled="loading"
            >
              {{ loading ? 'Création en cours...' : '✓ Créer la demande' }}
            </button>
          </div>

          <ErrorMessage v-if="error" :message="error" type="error" dismissible @dismiss="error = ''" />
        </div>
      </div>
    </div>

    <template #footer>
      <button @click="$emit('close')" class="btn btn-secondary">Annuler</button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import Modal from '@/components/common/Modal.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { useRequestsStore } from '@/stores/requests'
import type { SearchResult } from '@/types/api'

interface Props {
  media: SearchResult | null
  modelValue: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  close: []
  success: []
}>()

const requestsStore = useRequestsStore()

const isOpen = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const requestQuality = ref('1080p')
const loading = ref(false)
const error = ref('')

const mediaTypeLabel = computed(() => {
  if (!props.media) return ''
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

async function handleRequest() {
  if (!props.media) return

  loading.value = true
  error.value = ''

  const success = await requestsStore.createRequest({
    media_type: props.media.media_type,
    external_id: props.media.id,
    source: props.media.source,
    title: props.media.title,
    original_title: props.media.original_title,
    year: props.media.year,
    poster_url: props.media.poster_url,
    overview: props.media.overview,
    quality_preference: requestQuality.value,
  })

  loading.value = false

  if (success) {
    emit('success')
    emit('close')
  } else {
    error.value = requestsStore.error || 'Erreur lors de la création de la demande'
  }
}
</script>

<style scoped>
.media-details {
  max-width: 100%;
}

.details-content {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: var(--spacing-xl);
}

.poster-section img,
.poster-placeholder {
  width: 100%;
  aspect-ratio: 2 / 3;
  object-fit: cover;
  border-radius: var(--radius-md);
  background-color: var(--bg-dark);
}

.poster-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 4rem;
}

.info-section h3 {
  margin: 0 0 var(--spacing-sm) 0;
  color: var(--primary-color);
}

.original-title {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-md) 0;
}

.meta-info {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.meta-item {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.meta-item strong {
  color: var(--text-primary);
}

.overview {
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: var(--spacing-xl);
}

.overview.empty {
  font-style: italic;
}

.request-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.request-form label {
  font-weight: 500;
}

.btn-full {
  width: 100%;
  margin-top: var(--spacing-md);
}

@media (max-width: 768px) {
  .details-content {
    grid-template-columns: 1fr;
  }

  .poster-section {
    max-width: 200px;
    margin: 0 auto;
  }
}
</style>

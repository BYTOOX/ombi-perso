<template>
  <span class="status-badge" :class="`status-${status}`">
    <span class="icon">{{ icon }}</span>
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RequestStatus } from '@/types/api'

interface Props {
  status: RequestStatus
}

const props = defineProps<Props>()

const statusConfig = computed(() => {
  const configs: Record<
    RequestStatus,
    { icon: string; label: string }
  > = {
    pending: { icon: '⏳', label: 'En attente' },
    searching: { icon: '🔍', label: 'Recherche' },
    awaiting_approval: { icon: '⚠️', label: 'Approbation requise' },
    downloading: { icon: '⬇️', label: 'Téléchargement' },
    processing: { icon: '⚙️', label: 'Traitement' },
    completed: { icon: '✅', label: 'Complété' },
    error: { icon: '❌', label: 'Erreur' },
    cancelled: { icon: '🚫', label: 'Annulé' },
  }
  return configs[props.status] || { icon: '❓', label: props.status }
})

const icon = computed(() => statusConfig.value.icon)
const label = computed(() => statusConfig.value.label)
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 4px var(--spacing-sm);
  border-radius: var(--radius-md);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.icon {
  font-size: 1rem;
}

/* Status colors */
.status-pending,
.status-searching,
.status-awaiting_approval {
  background-color: rgba(245, 158, 11, 0.15);
  color: var(--warning-color);
  border: 1px solid var(--warning-color);
}

.status-downloading,
.status-processing {
  background-color: rgba(229, 160, 13, 0.15);
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
}

.status-completed {
  background-color: rgba(22, 163, 74, 0.15);
  color: var(--success-color);
  border: 1px solid var(--success-color);
}

.status-error {
  background-color: rgba(220, 38, 38, 0.15);
  color: var(--error-color);
  border: 1px solid var(--error-color);
}

.status-cancelled {
  background-color: rgba(115, 115, 115, 0.15);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}
</style>

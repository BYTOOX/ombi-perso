<template>
  <div v-if="message" class="error-message" :class="type">
    <span class="icon">{{ icon }}</span>
    <div class="content">
      <p class="message-text">{{ message }}</p>
      <button v-if="dismissible" @click="$emit('dismiss')" class="dismiss-btn">
        ✕
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  message?: string
  type?: 'error' | 'warning' | 'success' | 'info'
  dismissible?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  message: '',
  type: 'error',
  dismissible: false,
})

defineEmits<{
  dismiss: []
}>()

const icon = computed(() => {
  switch (props.type) {
    case 'error':
      return '❌'
    case 'warning':
      return '⚠️'
    case 'success':
      return '✅'
    case 'info':
      return 'ℹ️'
    default:
      return '❌'
  }
})
</script>

<style scoped>
.error-message {
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  border: 1px solid;
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.error-message.error {
  background-color: rgba(220, 38, 38, 0.1);
  border-color: var(--error-color);
  color: var(--error-color);
}

.error-message.warning {
  background-color: rgba(245, 158, 11, 0.1);
  border-color: var(--warning-color);
  color: var(--warning-color);
}

.error-message.success {
  background-color: rgba(22, 163, 74, 0.1);
  border-color: var(--success-color);
  color: var(--success-color);
}

.error-message.info {
  background-color: rgba(59, 130, 246, 0.1);
  border-color: #3b82f6;
  color: #3b82f6;
}

.icon {
  font-size: 1.25rem;
  flex-shrink: 0;
}

.content {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--spacing-md);
}

.message-text {
  margin: 0;
  flex: 1;
}

.dismiss-btn {
  background: none;
  border: none;
  color: inherit;
  font-size: 1.25rem;
  cursor: pointer;
  padding: 0;
  opacity: 0.6;
  transition: opacity var(--transition-fast);
}

.dismiss-btn:hover {
  opacity: 1;
}
</style>

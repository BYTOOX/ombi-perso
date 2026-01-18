<template>
  <div class="loading-spinner" :class="{ 'is-fullscreen': fullscreen }">
    <div class="spinner" :style="{ width: size, height: size }"></div>
    <p v-if="message" class="loading-message">{{ message }}</p>
  </div>
</template>

<script setup lang="ts">
interface Props {
  fullscreen?: boolean
  size?: string
  message?: string
}

withDefaults(defineProps<Props>(), {
  fullscreen: false,
  size: '40px',
  message: '',
})
</script>

<style scoped>
.loading-spinner {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: var(--spacing-2xl);
}

.loading-spinner.is-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(15, 15, 15, 0.95);
  z-index: 9999;
}

.spinner {
  border: 3px solid var(--border-color);
  border-top: 3px solid var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.loading-message {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin: 0;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>

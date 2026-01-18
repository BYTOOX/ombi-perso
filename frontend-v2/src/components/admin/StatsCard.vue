<template>
  <div class="stats-card" :class="`stats-${variant}`">
    <div class="stats-icon">
      {{ icon }}
    </div>
    <div class="stats-content">
      <div class="stats-label">{{ label }}</div>
      <div class="stats-value">{{ formattedValue }}</div>
      <div v-if="subtitle" class="stats-subtitle">{{ subtitle }}</div>
    </div>
    <div v-if="trend !== undefined" class="stats-trend" :class="trendClass">
      {{ trendIndicator }} {{ Math.abs(trend) }}%
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  label: string
  value: number | string
  icon: string
  variant?: 'primary' | 'success' | 'warning' | 'error' | 'info'
  subtitle?: string
  trend?: number
  formatAsNumber?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  formatAsNumber: true,
})

const formattedValue = computed(() => {
  if (typeof props.value === 'string') return props.value

  if (props.formatAsNumber) {
    return new Intl.NumberFormat('fr-FR').format(props.value)
  }

  return props.value
})

const trendClass = computed(() => {
  if (props.trend === undefined) return ''
  return props.trend >= 0 ? 'trend-up' : 'trend-down'
})

const trendIndicator = computed(() => {
  if (props.trend === undefined) return ''
  return props.trend >= 0 ? '↑' : '↓'
})
</script>

<style scoped>
.stats-card {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  transition: all var(--transition-normal);
  position: relative;
  overflow: hidden;
}

.stats-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: var(--primary-color);
  transition: all var(--transition-normal);
}

.stats-card:hover {
  border-color: var(--primary-color);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.stats-primary::before {
  background: var(--primary-color);
}

.stats-success::before {
  background: var(--success-color);
}

.stats-warning::before {
  background: var(--warning-color);
}

.stats-error::before {
  background: var(--error-color);
}

.stats-info::before {
  background: #3b82f6;
}

.stats-icon {
  font-size: 2.5rem;
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(229, 160, 13, 0.1);
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.stats-primary .stats-icon {
  background: rgba(229, 160, 13, 0.1);
}

.stats-success .stats-icon {
  background: rgba(22, 163, 74, 0.1);
}

.stats-warning .stats-icon {
  background: rgba(245, 158, 11, 0.1);
}

.stats-error .stats-icon {
  background: rgba(220, 38, 38, 0.1);
}

.stats-info .stats-icon {
  background: rgba(59, 130, 246, 0.1);
}

.stats-content {
  flex: 1;
  min-width: 0;
}

.stats-label {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-xs);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 500;
}

.stats-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  margin-bottom: var(--spacing-xs);
}

.stats-subtitle {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.stats-trend {
  font-size: 0.875rem;
  font-weight: 600;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  white-space: nowrap;
}

.trend-up {
  background: rgba(22, 163, 74, 0.15);
  color: var(--success-color);
}

.trend-down {
  background: rgba(220, 38, 38, 0.15);
  color: var(--error-color);
}

@media (max-width: 768px) {
  .stats-card {
    padding: var(--spacing-md);
  }

  .stats-icon {
    font-size: 2rem;
    width: 50px;
    height: 50px;
  }

  .stats-value {
    font-size: 1.5rem;
  }

  .stats-trend {
    position: absolute;
    top: var(--spacing-sm);
    right: var(--spacing-sm);
    font-size: 0.75rem;
  }
}
</style>

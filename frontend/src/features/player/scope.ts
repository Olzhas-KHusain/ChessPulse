import type { Scope, TimeClass } from '../../types/api';

export const TIME_CLASS_OPTIONS: ReadonlyArray<{ value: TimeClass; label: string }> = [
  { value: 'rapid', label: 'Rapid' },
  { value: 'blitz', label: 'Blitz' },
  { value: 'bullet', label: 'Bullet' },
  { value: 'daily', label: 'Daily' },
  { value: 'all', label: 'All classes' },
];

export const PERIOD_OPTIONS: ReadonlyArray<{ value: number; label: string }> = [
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
  { value: 180, label: 'Last 180 days' },
  { value: 365, label: 'Last 365 days' },
];

export const DEFAULT_SCOPE: Scope = { timeClass: 'rapid', days: 30 };

export function scopeKey(scope: Scope): string {
  return `${scope.timeClass}|${scope.days}`;
}

export function timeClassLabel(timeClass: TimeClass): string {
  return TIME_CLASS_OPTIONS.find((option) => option.value === timeClass)?.label ?? timeClass;
}

export function periodLabel(days: number): string {
  return `Last ${days} days`;
}

export function scopeQuery(scope: Scope): { time_class: TimeClass; days: number } {
  return { time_class: scope.timeClass, days: scope.days };
}

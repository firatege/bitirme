import type { SkuDetail, WinningCombo } from './schema';

export type UrgencyLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';

export function urgencyOf(win: WinningCombo | null | undefined): UrgencyLevel {
  if (!win) return 'UNKNOWN';
  const p3 = win.p_stockout_3m ?? null;
  const p6 = win.p_stockout_6m ?? null;
  const et = win.e_t_stockout_mo ?? null;
  if (p3 !== null && p3 >= 0.5) return 'CRITICAL';
  if (p3 !== null && p3 >= 0.25) return 'HIGH';
  if (p6 !== null && p6 >= 0.5) return 'HIGH';
  if (p6 !== null && p6 >= 0.25) return 'MEDIUM';
  if (et !== null && et <= 6) return 'MEDIUM';
  if (p3 !== null || p6 !== null) return 'LOW';
  return 'UNKNOWN';
}

export const urgencyRank: Record<UrgencyLevel, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
  UNKNOWN: 4,
};

export function needsReorder(detail: SkuDetail | null | undefined): boolean {
  const rec = detail?.recommendation;
  if (!rec) return false;
  return rec.order_qty_rounded > 0;
}

export function urgencyColorClass(level: UrgencyLevel): string {
  switch (level) {
    case 'CRITICAL':
      return 'bg-rose-100 text-rose-800 ring-rose-300 dark:bg-rose-500/15 dark:text-rose-300 dark:ring-rose-500/40';
    case 'HIGH':
      return 'bg-orange-100 text-orange-800 ring-orange-300 dark:bg-orange-500/15 dark:text-orange-300 dark:ring-orange-500/40';
    case 'MEDIUM':
      return 'bg-amber-100 text-amber-800 ring-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-500/40';
    case 'LOW':
      return 'bg-teal-100 text-teal-800 ring-teal-300 dark:bg-teal-500/15 dark:text-teal-300 dark:ring-teal-500/40';
    default:
      return 'bg-stone-100 text-stone-700 ring-stone-300 dark:bg-surface-2 dark:text-stone-300 dark:ring-surface-line';
  }
}

/**
 * Saf renk (background veya dot için) — urgency seviyesine göre.
 */
export function urgencyDotColor(level: UrgencyLevel): string {
  switch (level) {
    case 'CRITICAL':
      return '#dc2626';
    case 'HIGH':
      return '#ea580c';
    case 'MEDIUM':
      return '#ca8a04';
    case 'LOW':
      return '#0d9488';
    default:
      return '#64748b';
  }
}

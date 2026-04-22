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
      return 'bg-red-100 text-red-800 ring-red-300';
    case 'HIGH':
      return 'bg-orange-100 text-orange-800 ring-orange-300';
    case 'MEDIUM':
      return 'bg-yellow-100 text-yellow-800 ring-yellow-300';
    case 'LOW':
      return 'bg-green-100 text-green-800 ring-green-300';
    default:
      return 'bg-slate-100 text-slate-700 ring-slate-300';
  }
}

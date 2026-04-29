const STORAGE_KEY = 'seen_skus';

/** Persist a SKU code so it appears in the list even if the static file is missing. */
export function rememberSku(sku: string): void {
  const set = new Set(readSeenSkus());
  set.add(sku);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    // ignore quota errors
  }
}

/** Read all previously-seen SKU codes from localStorage. */
export function readSeenSkus(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : [];
  } catch {
    return [];
  }
}

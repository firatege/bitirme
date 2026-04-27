const STORAGE_KEY = 'bitirme-seen-skus-v1';

export function readSeenSkus(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is string => typeof x === 'string');
  } catch {
    return [];
  }
}

export function rememberSku(sku: string): void {
  if (!sku) return;
  try {
    const existing = new Set(readSeenSkus());
    existing.add(sku);
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...existing].sort()));
  } catch {
    /* ignore */
  }
}

export function rememberMany(skus: readonly string[]): void {
  try {
    const existing = new Set(readSeenSkus());
    skus.forEach((s) => s && existing.add(s));
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...existing].sort()));
  } catch {
    /* ignore */
  }
}

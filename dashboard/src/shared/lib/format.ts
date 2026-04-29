const intFmt = new Intl.NumberFormat('tr-TR', {
  maximumFractionDigits: 0,
});

const decFmt = new Intl.NumberFormat('tr-TR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const pctFmt = new Intl.NumberFormat('tr-TR', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Format integer, e.g. 12345 → "12.345" */
export function fmtInt(v: number | null | undefined): string {
  return v == null ? '—' : intFmt.format(v);
}

/** Format decimal, e.g. 3.14159 → "3,14" */
export function fmtDec(v: number | null | undefined): string {
  return v == null ? '—' : decFmt.format(v);
}

/** Format percentage (value already 0-1), e.g. 0.123 → "%12,3" */
export function fmtPct(v: number | null | undefined): string {
  return v == null ? '—' : pctFmt.format(v);
}

/** Format months, e.g. 4 → "4 ay" */
export function fmtMonths(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${fmtDec(v)} ay`;
}

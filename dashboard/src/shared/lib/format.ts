const nfInt = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const nfDec = new Intl.NumberFormat('tr-TR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 2,
});
const pct = new Intl.NumberFormat('tr-TR', {
  style: 'percent',
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
});

export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return nfInt.format(n);
}

export function fmtDec(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return nfDec.format(n);
}

export function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return pct.format(n);
}

export function fmtMonths(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `${nfDec.format(n)} ay`;
}

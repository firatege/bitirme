#!/usr/bin/env node
/**
 * Reads ../panel_sales_orders_stock.csv and writes public/sku_list.json
 * with the unique SKU set. Idempotent; safe to call from `npm run prebuild`.
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const CSV_PATH = resolve(ROOT, '..', 'panel_sales_orders_stock.csv');
const OUT_PATH = resolve(ROOT, 'public', 'sku_list.json');

if (!existsSync(CSV_PATH)) {
  console.warn(`[gen-sku-list] CSV not found at ${CSV_PATH}; skipping.`);
  process.exit(0);
}

const csv = readFileSync(CSV_PATH, 'utf-8');
const lines = csv.split(/\r?\n/);
if (lines.length === 0) {
  console.warn('[gen-sku-list] empty CSV; skipping.');
  process.exit(0);
}

const header = lines[0].split(',').map((s) => s.trim());
const skuIdx = header.indexOf('sku');
if (skuIdx === -1) {
  console.error('[gen-sku-list] no `sku` column in CSV header; aborting.');
  process.exit(1);
}

const set = new Set();
for (let i = 1; i < lines.length; i++) {
  const line = lines[i];
  if (!line) continue;
  const cols = line.split(',');
  const sku = (cols[skuIdx] ?? '').trim();
  if (sku) set.add(sku);
}

const skus = [...set].sort();

mkdirSync(dirname(OUT_PATH), { recursive: true });
writeFileSync(OUT_PATH, JSON.stringify({ skus }, null, 2) + '\n');
console.log(`[gen-sku-list] wrote ${skus.length} SKUs → ${OUT_PATH}`);

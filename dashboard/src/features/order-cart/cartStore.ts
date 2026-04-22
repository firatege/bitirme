import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface CartItem {
  sku: string;
  suggested_qty: number;
  approved_qty: number;
  note?: string;
  added_at: string;
}

interface CartState {
  items: Record<string, CartItem>;
  add: (item: Omit<CartItem, 'added_at'>) => void;
  update: (sku: string, patch: Partial<CartItem>) => void;
  remove: (sku: string) => void;
  clear: () => void;
}

export const useCartStore = create<CartState>()(
  persist(
    (set) => ({
      items: {},
      add: (item) =>
        set((state) => ({
          items: {
            ...state.items,
            [item.sku]: { ...item, added_at: new Date().toISOString() },
          },
        })),
      update: (sku, patch) =>
        set((state) => {
          const existing = state.items[sku];
          if (!existing) return state;
          return {
            items: { ...state.items, [sku]: { ...existing, ...patch } },
          };
        }),
      remove: (sku) =>
        set((state) => {
          const next = { ...state.items };
          delete next[sku];
          return { items: next };
        }),
      clear: () => set({ items: {} }),
    }),
    { name: 'bitirme-cart-v1' },
  ),
);

export function cartCount(items: Record<string, CartItem>): number {
  return Object.keys(items).length;
}

export function cartTotalQty(items: Record<string, CartItem>): number {
  return Object.values(items).reduce((sum, i) => sum + i.approved_qty, 0);
}

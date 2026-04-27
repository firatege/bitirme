import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type RunTrigger = 'all' | 'sku';

export interface RunHistoryEntry {
  run_id: number;
  trigger: RunTrigger;
  sku?: string;
  recorded_at: string;
}

interface RunHistoryStore {
  entries: RunHistoryEntry[];
  record: (entry: Omit<RunHistoryEntry, 'recorded_at'>) => void;
  clear: () => void;
}

const MAX = 50;

export const useRunHistoryStore = create<RunHistoryStore>()(
  persist(
    (set) => ({
      entries: [],
      record: (entry) =>
        set((state) => {
          if (state.entries.some((e) => e.run_id === entry.run_id)) {
            return state;
          }
          const next: RunHistoryEntry = {
            ...entry,
            recorded_at: new Date().toISOString(),
          };
          return {
            entries: [next, ...state.entries].slice(0, MAX),
          };
        }),
      clear: () => set({ entries: [] }),
    }),
    { name: 'bitirme-run-history-v1' },
  ),
);

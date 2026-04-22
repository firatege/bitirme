import { z } from 'zod';

export const RunStatusSchema = z.object({
  run_id: z.number(),
  status: z.enum(['queued', 'running', 'completed', 'failed']),
  started_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  pipeline_version: z.string().nullable().optional(),
  jobs: z
    .object({
      queued: z.number().default(0),
      running: z.number().default(0),
      completed: z.number().default(0),
      failed: z.number().default(0),
    })
    .default({ queued: 0, running: 0, completed: 0, failed: 0 }),
});
export type RunStatus = z.infer<typeof RunStatusSchema>;

export const CreateRunResponseSchema = z.object({
  run_id: z.number(),
  jobs: z.number(),
  status: z.string(),
});
export type CreateRunResponse = z.infer<typeof CreateRunResponseSchema>;

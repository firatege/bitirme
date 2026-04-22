import { useState } from 'react';
import { Button } from '@/shared/ui/Button';
import { useCreateRun, useRunStatus } from '@/shared/api/hooks';

export function RunTrigger() {
  const [runId, setRunId] = useState<number | null>(null);
  const create = useCreateRun();
  const status = useRunStatus(runId);

  const handleRun = async () => {
    const res = await create.mutateAsync({ concurrency: 4, check_drift: true });
    setRunId(res.run_id);
  };

  return (
    <div className="flex items-center gap-3">
      <Button
        onClick={handleRun}
        disabled={create.isPending}
        variant="primary"
      >
        {create.isPending ? 'Tetikleniyor…' : 'Tümünü Çalıştır'}
      </Button>
      {runId && status.data && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-500">Run #{runId}</span>
          <StatusBadge status={status.data.status} />
          <span className="text-slate-500">
            {status.data.jobs.completed}/
            {status.data.jobs.completed +
              status.data.jobs.running +
              status.data.jobs.queued +
              status.data.jobs.failed}
          </span>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    queued: 'bg-slate-100 text-slate-700 ring-slate-200',
    running: 'bg-blue-100 text-blue-700 ring-blue-200',
    completed: 'bg-green-100 text-green-700 ring-green-200',
    failed: 'bg-red-100 text-red-700 ring-red-200',
  };
  return (
    <span
      className={`rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
        map[status] ?? map['queued']
      }`}
    >
      {status}
    </span>
  );
}

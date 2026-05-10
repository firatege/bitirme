import { useParams, Link } from 'react-router-dom';
import { useRunStatus } from '@/shared/api/hooks';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Stat } from '@/shared/ui/Stat';
import { Skeleton } from '@/shared/ui/Skeleton';
import { ErrorState } from '@/shared/ui/ErrorState';
import { fmtInt } from '@/shared/lib/format';

const STATUS_TONES: Record<string, string> = {
  queued:
    'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-surface-2 dark:text-stone-300 dark:ring-surface-line',
  running:
    'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-500/30',
  completed:
    'bg-brand-100 text-brand-800 ring-brand-200 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-500/30',
  failed:
    'bg-rose-100 text-rose-700 ring-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:ring-rose-500/30',
};

export function RunDetailPage() {
  const { runId = '' } = useParams<{ runId: string }>();
  const idNum = Number(runId);
  const status = useRunStatus(Number.isFinite(idNum) ? idNum : null);

  if (status.isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }
  if (status.isError || !status.data) {
    return (
      <ErrorState
        title="Run bulunamadı"
        message={`#${runId} için durum okunamadı.`}
        onRetry={() => status.refetch()}
      />
    );
  }

  const s = status.data;
  const total =
    s.jobs.queued + s.jobs.running + s.jobs.completed + s.jobs.failed;
  const pct = total > 0 ? Math.round((s.jobs.completed / total) * 100) : 0;
  const statusTone = STATUS_TONES[s.status] ?? STATUS_TONES.queued;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          to="/runs"
          className="text-xs text-slate-500 hover:text-slate-800 dark:text-stone-400 dark:hover:text-stone-100"
        >
          ← Çalışmalar
        </Link>
        <h1 className="font-mono text-xl font-medium text-slate-900 dark:text-stone-50">
          #{idNum}
        </h1>
        <span
          className={`rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${statusTone}`}
        >
          {s.status}
        </span>
        <div className="ml-auto text-xs text-slate-500 dark:text-stone-400">
          {pct}% tamam
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Toplam Job" value={fmtInt(total)} tone="brand" />
        <Stat
          label="Tamamlanan"
          value={fmtInt(s.jobs.completed)}
          tone="success"
          hint={`${pct}% tamam`}
        />
        <Stat label="Çalışan" value={fmtInt(s.jobs.running)} />
        <Stat
          label="Başarısız"
          value={fmtInt(s.jobs.failed)}
          tone={s.jobs.failed > 0 ? 'critical' : 'default'}
        />
      </div>

      <Card>
        <CardHeader title="Detaylar" />
        <CardBody className="space-y-1.5 text-sm">
          <Row label="Run ID" value={`#${s.run_id}`} />
          <Row label="Pipeline sürümü" value={s.pipeline_version ?? '—'} />
          <Row label="Başlangıç" value={s.started_at ?? '—'} />
          <Row label="Bitiş" value={s.completed_at ?? '—'} />
          <Row label="Kuyrukta" value={fmtInt(s.jobs.queued)} />
        </CardBody>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-1.5 last:border-0 dark:border-surface-line/60">
      <span className="text-slate-500 dark:text-stone-400">{label}</span>
      <span className="font-mono text-xs text-slate-700 dark:text-stone-200">
        {value}
      </span>
    </div>
  );
}

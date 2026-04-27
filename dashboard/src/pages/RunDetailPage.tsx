import { useParams, Link } from 'react-router-dom';
import { useRunStatus } from '@/shared/api/hooks';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Stat } from '@/shared/ui/Stat';
import { Skeleton } from '@/shared/ui/Skeleton';
import { ErrorState } from '@/shared/ui/ErrorState';
import { fmtInt } from '@/shared/lib/format';

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

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/runs" className="text-xs text-slate-500 hover:text-slate-800">
          ← Çalışmalar
        </Link>
        <h1 className="text-2xl font-semibold text-slate-900">Run #{idNum}</h1>
        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium ring-1 ring-inset ring-slate-200">
          {s.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Toplam Job" value={fmtInt(total)} />
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
        <CardBody className="space-y-2 text-sm">
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
    <div className="flex justify-between border-b border-slate-100 py-1 last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono text-xs text-slate-700">{value}</span>
    </div>
  );
}

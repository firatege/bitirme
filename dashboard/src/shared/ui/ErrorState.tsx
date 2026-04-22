import { Button } from './Button';

export function ErrorState({
  title,
  message,
  onRetry,
}: {
  title: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-5">
      <h3 className="text-sm font-semibold text-red-800">{title}</h3>
      {message && <p className="mt-1 text-xs text-red-700">{message}</p>}
      {onRetry && (
        <div className="mt-3">
          <Button size="sm" variant="secondary" onClick={onRetry}>
            Yeniden dene
          </Button>
        </div>
      )}
    </div>
  );
}

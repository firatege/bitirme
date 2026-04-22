import { useCartStore, cartCount } from './cartStore';
import { cartToCsv, downloadCsv } from './exportCsv';
import { Button } from '@/shared/ui/Button';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { EmptyState } from '@/shared/ui/EmptyState';
import { fmtInt } from '@/shared/lib/format';

export function CartView() {
  const items = useCartStore((s) => s.items);
  const update = useCartStore((s) => s.update);
  const remove = useCartStore((s) => s.remove);
  const clear = useCartStore((s) => s.clear);

  const rows = Object.values(items);

  if (cartCount(items) === 0) {
    return (
      <EmptyState
        title="Sepet boş"
        description="SKU detay sayfasından 'Sepete Ekle' ile öneri ekleyin."
      />
    );
  }

  const handleExport = () => {
    const csv = cartToCsv(rows);
    const ts = new Date().toISOString().slice(0, 10);
    downloadCsv(csv, `siparis-onerisi-${ts}.csv`);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Button onClick={handleExport}>CSV İndir</Button>
        <Button variant="secondary" onClick={clear}>
          Sepeti Boşalt
        </Button>
        <span className="ml-auto text-xs text-slate-500">
          {rows.length} SKU · Toplam {fmtInt(
            rows.reduce((s, r) => s + r.approved_qty, 0),
          )}{' '}
          adet
        </span>
      </div>
      <Card>
        <CardHeader title="Onay Bekleyen Siparişler" />
        <CardBody className="p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left">SKU</th>
                <th className="px-4 py-3 text-right">Önerilen</th>
                <th className="px-4 py-3 text-right">Onaylanan</th>
                <th className="px-4 py-3 text-left">Not</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.sku}
                  className="border-b border-slate-100 last:border-0"
                >
                  <td className="px-4 py-3 font-mono text-xs">{r.sku}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {fmtInt(r.suggested_qty)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <input
                      type="number"
                      value={r.approved_qty}
                      onChange={(e) =>
                        update(r.sku, { approved_qty: Number(e.target.value) })
                      }
                      className="w-24 rounded-md border border-slate-200 px-2 py-1 text-right tabular-nums"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      value={r.note ?? ''}
                      onChange={(e) => update(r.sku, { note: e.target.value })}
                      placeholder="Not…"
                      className="w-full rounded-md border border-slate-200 px-2 py-1 text-sm"
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => remove(r.sku)}
                    >
                      Kaldır
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>
    </div>
  );
}

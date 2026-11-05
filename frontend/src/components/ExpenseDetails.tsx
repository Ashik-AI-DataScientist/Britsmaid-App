import React, { useState } from 'react';
import { View } from 'react-native';
import { useAuth } from '@/src/auth';
import { api } from '@/src/api';
import { Button, Card, Row, Txt } from '@/src/ui';
import { MediaThumb } from '@/src/components/MediaThumb';
import { fmtDate, inr } from '@/src/format';

function Evidence({ ids }: { ids: string[] }) {
  const [open, setOpen] = useState(false);
  if (!ids?.length) return null;
  return <><Button small variant="secondary" title={`${open ? 'Hide' : 'View'} attachments (${ids.length})`} onPress={() => setOpen(!open)} />
    {open ? <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>{ids.map(id => <MediaThumb key={id} id={id} kind="image" size={96} />)}</View> : null}</>;
}
export function expenseTreatment(item: any) {
  return item.treatment || (item.type === 'pre_split' ? 'before_split' : item.type === 'electricity' && item.owner_amount === 0 && item.britsmaid_amount === 0 && !item.allocation ? 'reference' : 'after_split');
}
function Shares({ item }: { item: any }) {
  if (expenseTreatment(item) !== 'after_split') return null;
  const a = item.allocation;
  const owner = a?.owner_amount ?? item.owner_amount, bm = a?.britsmaid_amount ?? item.britsmaid_amount;
  if (owner == null && bm == null) return <Txt v="caption">Allocation detail was not included in this saved statement.</Txt>;
  return <>
    {owner > 0 ? <Row label={bm > 0 ? `Owner${a?.owner_percent != null ? ` (${a.owner_percent}%)` : ''}` : 'Owner bears the full expense'} value={inr(owner)} /> : null}
    {bm > 0 ? <Row label={owner > 0 ? `Britsmaid${a?.britsmaid_percent != null ? ` (${a.britsmaid_percent}%)` : ''}` : 'Britsmaid bears the full expense'} value={inr(bm)} /> : null}
  </>;
}
export function ExpenseDetails({ item, onEdit }: { item: any; onEdit?: (item: any) => void }) {
  const [open, setOpen] = useState(false), [history, setHistory] = useState<any>(null), [historyOpen, setHistoryOpen] = useState(false), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const { user } = useAuth();
  const treatment = expenseTreatment(item);
  const loadHistory = async () => {
    if (historyOpen) { setHistoryOpen(false); return; }
    setLoading(true); setError('');
    try { setHistory(await api.get(`/expenses/${item.id}/history`)); setHistoryOpen(true); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };
  return <View style={{ gap: 8 }}>
    <Button small variant="ghost" title={`${item.title || (item.type === 'electricity' ? 'Electricity' : 'Other expense')} · ${inr(item.amount)} · ${open ? 'Hide' : 'Details'}`} onPress={() => setOpen(!open)} />
    {open ? <View style={{ gap: 8 }}>
      <Txt>{item.notes || 'No additional note recorded'}</Txt>
      <Txt v="caption">{treatment === 'before_split' ? 'Deducted before the revenue split; not deducted again from either share.' : treatment === 'reference' ? 'Reference only: paid directly by the owner, not deducted from the payout.' : 'Deducted after the revenue split.'}</Txt>
      {item.source === 'booking' ? <Txt v="caption">Recorded in the booking breakdown; shown here once for reference.</Txt> : null}
      <Shares item={item} />
      {item.last_change_reason ? <Txt v="caption">Updated {fmtDate(item.updated_at)}: {item.last_change_reason}</Txt> : null}
      <Evidence ids={item.media_ids || []} />
      {user?.role === 'admin' && onEdit ? <Button small variant="secondary" title={item.booking_id ? 'Edit in booking' : 'Edit expense'} onPress={() => onEdit(item)} /> : null}
      {/^[a-f\d]{24}$/i.test(item.id || '') ? <Button small variant="ghost" title={historyOpen ? 'Hide change history' : 'View change history'} onPress={loadHistory} loading={loading} /> : null}
      {error ? <Card><Txt>{error}</Txt></Card> : null}
      {historyOpen && history ? <>
        {history.current_revision !== (item.revision || 0) ? <Txt>This view contains a saved version. The current record is revision {history.current_revision}; the saved amounts above have not been replaced.</Txt> : null}
        {history.is_deleted ? <Txt>This expense has since been removed from current statements. Previous evidence remains available.</Txt> : null}
        {!history.entries.length ? <Txt v="caption">No changes recorded for this expense.</Txt> : history.entries.map((h: any, i: number) => <Card key={`${h.at}-${i}`}>
          <Txt v="label">{h.action === 'removed' ? 'Removed' : 'Edited'} · {fmtDate(h.at)}</Txt><Txt>{h.reason}</Txt>
          <Txt>{h.before.title} · {h.before.month}</Txt><Txt>{h.before.notes || 'No additional note recorded'}</Txt><Row label="Previous amount" value={inr(h.before.amount)} /><Txt v="caption">Previous treatment: {expenseTreatment(h.before).replace('_', ' ')}</Txt><Shares item={h.before} /><Evidence ids={h.before.media_ids || []} />
          {h.after ? <><Txt>{h.after.title} · {h.after.month}</Txt><Txt>{h.after.notes || 'No additional note recorded'}</Txt><Row label="Updated amount" value={inr(h.after.amount)} /><Txt v="caption">Updated treatment: {expenseTreatment(h.after).replace('_', ' ')}</Txt><Shares item={h.after} /></> : null}
        </Card>)}
      </> : null}
    </View> : null}
  </View>;
}

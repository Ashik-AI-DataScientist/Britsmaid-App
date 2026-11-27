import React, { useRef, useState } from 'react';
import { View } from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/src/auth';
import { api, request } from '@/src/api';
import { allocationMath, money } from '@/src/booking-finance';
import { CaptureSheet, Media } from '@/src/components/CaptureSheet';
import { Button, Card, Chip, ConfirmSheet, Input, Row, Sheet, Txt, useToast } from '@/src/ui';
import { inr, thisMonth } from '@/src/format';
import { spacing, useTheme } from '@/src/theme';

export function ExpenseEditor({ propertyId, item, initialMonth, initialTreatment, onClose }: {
  propertyId: string; item?: any; initialMonth?: string; initialTreatment?: string; onClose: () => void;
}) {
  const { user } = useAuth();
  const qc = useQueryClient(), toast = useToast();
  const { colors } = useTheme();
  const [f, setF] = useState({ title: item?.title || '', amount: item ? String(item.amount) : '', month: item?.month || initialMonth || thisMonth(), notes: item?.notes || '', treatment: item?.treatment || initialTreatment || '', change_reason: '' });
  const [allocation, setAllocation] = useState<any>(item?.allocation ? { ...item.allocation, entry_mode: item.allocation.manual ? 'amount' : 'percent', amount_side: item.allocation.amount_side || 'owner' } : null);
  const [sharing, setSharing] = useState(item?.allocation ? Number(item.allocation.owner_amount) === 0 ? 'britsmaid' : Number(item.allocation.britsmaid_amount) === 0 ? 'owner' : 'shared' : '');
  const [media, setMedia] = useState<Media[]>((item?.media_ids || []).map((id: string) => ({ id, kind: 'image', content_type: 'image/jpeg' })));
  const [capture, setCapture] = useState(false), [confirm, setConfirm] = useState(false), [saving, setSaving] = useState(false), [error, setError] = useState('');
  const [captureKey] = useState(() => `expense-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const lock = useRef(false);
  const amount = Number(f.amount) || 0;
  const a = allocation ? allocationMath(amount, allocation) : null;
  const change = (field: string, value: string) => setF(old => ({ ...old, [field]: value }));
  const selectSharing = (side: string) => { setSharing(side); setAllocation({ owner_percent: side === 'owner' ? 100 : side === 'britsmaid' ? 0 : 50, britsmaid_percent: side === 'owner' ? 0 : side === 'britsmaid' ? 100 : 50, owner_amount: 0, britsmaid_amount: 0, entry_mode: 'percent', manual: false, amount_side: 'owner' }); };
  const save = async () => {
    if (lock.current) return;
    setError('');
    if (!f.title.trim()) return setError('Enter an expense title or description.');
    if (!Number.isFinite(Number(f.amount)) || Number(f.amount) <= 0) return setError('Enter a valid expense amount greater than zero.');
    if (!f.treatment) return setError('Choose before split or after split.');
    if (f.treatment === 'after_split' && !a) return setError('Choose who bears this expense.');
    if (allocation && f.treatment === 'after_split') {
      const field = allocation.entry_mode === 'amount' ? `${allocation.amount_side || 'owner'}_amount` : `${allocation.percent_side || 'owner'}_percent`;
      const raw = allocation[field];
      if (raw === '' || !Number.isFinite(Number(raw))) return setError('Enter a valid number for the expense share.');
    }
    if (a && f.treatment === 'after_split' && (a.owner_amount < 0 || a.britsmaid_amount < 0 || !Number.isFinite(a.owner_percent) || Number(a.owner_percent) < 0 || Number(a.owner_percent) > 100)) return setError('The two shares must be between zero and the total expense.');
    if (item && !f.change_reason.trim()) return setError('Enter a short reason for this change.');
    lock.current = true; setSaving(true);
    try {
      const body = { ...f, property_id: propertyId, amount: money(amount), type: f.treatment === 'before_split' ? 'pre_split' : 'other', allocation: f.treatment === 'after_split' ? a : null, media_ids: media.map(m => m.id), revision: item?.revision ?? 0, request_key: captureKey };
      if (item) await api.put(`/expenses/${item.id}`, body); else await api.post('/expenses', body);
      await qc.invalidateQueries(); toast(item ? 'Expense updated; statements refreshed' : 'Expense saved'); onClose();
    } catch (e: any) { setError(e.message || 'Could not save the expense. Your entries are kept.'); }
    finally { lock.current = false; setSaving(false); }
  };
  const remove = async () => {
    if (lock.current || !item) return;
    lock.current = true; setSaving(true);
    try { await request(`/expenses/${item.id}`, { method: 'DELETE', body: { revision: item.revision ?? 0, change_reason: f.change_reason } }); await qc.invalidateQueries(); toast('Expense removed; history and attachments retained'); onClose(); }
    catch (e: any) { setConfirm(false); setError(e.message); }
    finally { lock.current = false; setSaving(false); }
  };
  if (user?.role !== 'admin') return null;
  return <>
    <Sheet visible onClose={() => { if (!saving) onClose(); }} title={item ? 'Edit expense' : 'Add expense'} testID="expense-editor">
      <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" style={{ flexShrink: 1 }} contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.lg }}>
        <Input testID="expense-title" label="Expense title / description" value={f.title} onChangeText={v => change('title', v)} />
        <View style={{ flexDirection: 'row', gap: spacing.md }}>
          <View style={{ flex: 1 }}><Input testID="expense-amount" label="Amount ₹" keyboardType="decimal-pad" value={f.amount} onChangeText={v => change('amount', v)} /></View>
          <View style={{ flex: 1 }}><Input testID="expense-month" label="Statement month (YYYY-MM)" value={f.month} onChangeText={v => change('month', v)} /></View>
        </View>
        <Txt v="label">When should this expense be deducted?</Txt>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
          <Chip testID="expense-before" label="Before revenue split" selected={f.treatment === 'before_split'} onPress={() => change('treatment', 'before_split')} />
          <Chip testID="expense-after" label="After revenue split" selected={f.treatment === 'after_split'} onPress={() => change('treatment', 'after_split')} />
          {item?.treatment === 'reference' ? <Chip label="Keep reference only" selected={f.treatment === 'reference'} onPress={() => change('treatment', 'reference')} /> : null}
        </View>
        <Txt v="caption">{f.treatment === 'before_split' ? 'Deducted once from the common revenue pool before the owner and Britsmaid shares are calculated. No separate allocation applies.' : f.treatment === 'reference' ? 'This existing record was paid directly by the owner. It remains reference-only unless you explicitly choose a deduction treatment.' : 'First calculate the revenue split, then deduct this expense from the selected shares.'}</Txt>
        {f.treatment === 'after_split' ? <>
          <Txt v="label">Who bears this expense?</Txt>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>{[['owner', 'Owner pays all'], ['britsmaid', 'Britsmaid pays all'], ['shared', 'Share the expense']].map(([side, label]) => <Chip key={side} testID={`expense-sharing-${side}`} label={label} selected={sharing === side} onPress={() => selectSharing(side)} />)}</View>
          {allocation && sharing === 'shared' ? <>
            <Txt v="caption">Enter a percentage or an amount for either party. The other share and percentages update automatically.</Txt>
            {(['owner', 'britsmaid'] as const).map(side => <View key={side} style={{ gap: 6 }}><Txt v="label">{side === 'owner' ? 'Owner' : 'Britsmaid'}</Txt><View style={{ flexDirection: 'row', gap: spacing.md }}>
              <View style={{ flex: 1 }}><Input testID={`expense-${side}-percent`} label="Percentage %" keyboardType="decimal-pad" value={allocation.entry_mode === 'percent' && allocation.percent_side === side ? String(allocation[`${side}_percent`]) : a?.[`${side}_percent`] == null ? '' : String(a[`${side}_percent`])} onChangeText={v => setAllocation({ ...allocation, owner_percent: side === 'owner' ? v : 100 - Number(v), britsmaid_percent: side === 'britsmaid' ? v : 100 - Number(v), percent_side: side, entry_mode: 'percent', manual: false })} /></View>
              <View style={{ flex: 1 }}><Input testID={`expense-${side}-amount`} label="Amount ₹" keyboardType="decimal-pad" value={allocation.entry_mode === 'amount' && allocation.amount_side === side ? String(allocation[`${side}_amount`]) : String(a?.[`${side}_amount`] ?? 0)} onChangeText={v => setAllocation({ ...allocation, [`${side}_amount`]: v, amount_side: side, entry_mode: 'amount', manual: true })} /></View>
            </View></View>)}
          </> : null}
          {a ? <><Row label="Owner contribution" value={inr(a.owner_amount)} /><Row label="Britsmaid contribution" value={inr(a.britsmaid_amount)} /></> : null}
        </> : null}
        <Input testID="expense-notes" label="Notes / explanation" multiline value={f.notes} onChangeText={v => change('notes', v)} />
        <Button variant="secondary" title={`Attach photo · camera or library (${media.length}/10)`} onPress={() => setCapture(true)} disabled={saving} />
        {media.map((m, i) => <Button key={m.id} small variant="ghost" title={`Remove attachment ${i + 1} from this expense`} onPress={() => setMedia(old => old.filter(x => x.id !== m.id))} disabled={saving} />)}
        {item ? <><Input testID="expense-change-reason" label="Reason for this change (required)" multiline value={f.change_reason} onChangeText={v => change('change_reason', v)} /><Txt v="caption">Previous values and the reason are saved in the expense history. Existing issued reports stay unchanged; generate a new report to include this edit.</Txt></> : null}
        <Txt v="caption">Amounts round to two decimals. Owner TDS is calculated after all owner expenses in the monthly statement.</Txt>
        {error ? <Card><Txt color={colors.error}>{error}</Txt></Card> : null}
        <Button testID="expense-save" title={item ? 'Save expense changes' : 'Save expense'} onPress={save} loading={saving} />
        {item ? <Button variant="ghost" title="Remove expense" disabled={saving} onPress={() => { if (!f.change_reason.trim()) setError('Enter a reason before removing the expense.'); else setConfirm(true); }} /> : null}
      </KeyboardAwareScrollView>
    </Sheet>
    <CaptureSheet visible={capture} onClose={() => setCapture(false)} purpose="Expense evidence" destination={{ key: item ? `expense-${item.id}` : captureKey, label: 'Expense evidence' }} onUploaded={async uploaded => { const next = [...media, ...uploaded.filter(m => !media.some(x => x.id === m.id))]; if (next.length > 10) throw new Error('A maximum of ten photos can be attached. Remove an attachment before retrying.'); setMedia(next); }} />
    <ConfirmSheet visible={confirm} onClose={() => setConfirm(false)} title="Remove this expense?" message="It will stop contributing to current statements. Its edit history, evidence and saved report snapshots remain available." confirmLabel="Remove expense" onConfirm={remove} loading={saving} />
  </>;
}

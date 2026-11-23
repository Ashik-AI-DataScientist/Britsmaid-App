import React, { useState } from 'react';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { View } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/src/auth';
import { api } from '@/src/api';
import { Button, Card, Chip, Input, Row, Sheet, Txt, useToast } from '@/src/ui';
import { DateField } from './DateField';
import { inr } from '@/src/format';
import { money, percentAmount } from '@/src/booking-finance';

const newRevenueId = () => `revenue-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export function AdditionalRevenue({ booking, ownerPercent = 70 }: { booking: any; ownerPercent?: number }) {
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [form, setForm] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: string) => (value: string) => setForm((previous: any) => ({ ...previous, [key]: value }));
  const net = form ? money(Number(form.amount || 0) - Number(form.tax || 0) - Number(form.fee || 0)) : 0;
  const owner = form ? form.amountMode ? Number(form.owner_amount || 0) : percentAmount(net, Number(form.owner_percent || 0)) : 0;
  const open = (item?: any) => setForm(item ? { ...item, amountMode: item.owner_amount != null, revision: booking.revision ?? 0 } : {
    id: newRevenueId(), title: '', amount: '', tax: '', fee: '',
    owner_percent: ownerPercent, owner_amount: '', amountMode: false, service_date: booking.check_in, status: 'received', notes: '', revision: booking.revision ?? 0 });
  const save = async () => {
    if (busy || !form) return;
    setBusy(true);
    try {
      await api.post(`/bookings/${booking.id}/revenue`, { ...form, amount: Number(form.amount), tax: Number(form.tax || 0), fee: Number(form.fee || 0),
        owner_percent: Number(form.owner_percent), owner_amount: form.amountMode ? Number(form.owner_amount) : null });
      await qc.invalidateQueries(); setForm(null); toast('Additional revenue saved');
    } catch (error: any) { toast(error.message, 'error'); }
    finally { setBusy(false); }
  };
  return <Card style={{ gap: 12 }}>
    <Txt v="subtitle">Additional revenue</Txt>
    {(booking.additional_revenue ?? []).map((item: any) => <View key={item.id} style={{ gap: 6 }}>
      <Row label={`${item.title} · ${item.status}`} value={inr(item.amount)} />
      <Txt v="caption">{item.service_date} · {item.notes}</Txt>
      <Row label="Tax / fees" value={inr(money(item.tax + item.fee))} />
      <Row label="Owner allocation" value={inr(item.owner_amount ?? percentAmount(money(item.amount - item.tax - item.fee), item.owner_percent))} />
      <Txt v="caption">{item.status === 'received' ? 'Included in the service-date statement. Owner TDS is calculated in the monthly statement.' : 'Excluded from earned revenue until received.'}</Txt>
      {user?.role === 'admin' ? <Button small title="Correct / refund entry" variant="secondary" onPress={() => open(item)} /> : null}
    </View>)}
    {user?.role === 'admin' && booking.status === 'confirmed' ? <Button title="Add additional revenue" onPress={() => open()} /> : null}
    <Sheet testID="additional-revenue-sheet" visible={!!form} title="Additional revenue" onClose={() => { if (!busy) setForm(null); }}>
      {form ? <KeyboardAwareScrollView testID="additional-revenue-scroll" bottomOffset={24} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag" style={{ flexShrink: 1 }} contentContainerStyle={{ gap: 12, paddingBottom: 32 }}>
        <Input testID="revenue-title" label="Service / extra person" value={form.title} onChangeText={set('title')} />
        <Input testID="revenue-amount" label="Gross amount ₹" value={String(form.amount)} onChangeText={set('amount')} keyboardType="decimal-pad" />
        <Input label="Tax included ₹ (if recorded)" value={String(form.tax)} onChangeText={set('tax')} keyboardType="decimal-pad" />
        <Input label="Collection fee ₹ (if recorded)" value={String(form.fee)} onChangeText={set('fee')} keyboardType="decimal-pad" />
        <DateField testID="revenue-date" label="Service date / statement period" value={form.service_date} onChange={set('service_date')} />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <Chip label="Percentage split" selected={!form.amountMode} onPress={() => setForm({ ...form, amountMode: false })} />
          <Chip label="Amount split" selected={form.amountMode} onPress={() => setForm({ ...form, amountMode: true })} />
        </View>
        {form.amountMode ? <Input label="Owner allocation ₹" value={String(form.owner_amount)} onChangeText={set('owner_amount')} keyboardType="decimal-pad" /> :
          <Input label="Owner share %" value={String(form.owner_percent)} onChangeText={set('owner_percent')} keyboardType="decimal-pad" />}
        <Txt>Net {inr(net)} · Owner {inr(owner)} · Britsmaid {inr(money(net - owner))}</Txt>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{['received', 'pending', 'refunded'].map(status =>
          <Chip key={status} label={status[0].toUpperCase() + status.slice(1)} selected={form.status === status} onPress={() => set('status')(status)} />)}</View>
        <Input testID="revenue-notes" label="Notes / correction reason" multiline value={form.notes} onChangeText={set('notes')} />
        <Button testID="revenue-save" title="Save additional revenue" loading={busy} disabled={!form.title.trim() || net < 0 || owner < 0 || owner > net} onPress={save} />
      </KeyboardAwareScrollView> : null}
    </Sheet>
  </Card>;
}

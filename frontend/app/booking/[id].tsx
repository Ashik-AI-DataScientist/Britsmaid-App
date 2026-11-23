import React, { useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth';
import { AdditionalRevenue } from '@/src/components/AdditionalRevenue';
import { BookingAmounts } from '@/src/components/BookingAmounts';
import { Button, Card, ErrorState, Header, Loading, Row, Txt, Input, useToast } from '@/src/ui';
import { inr } from '@/src/format';

export default function BookingDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [savingCancel, setSavingCancel] = useState(false);
  const { user } = useAuth();
  const q = useQuery({ queryKey: ['booking', id], queryFn: () => api.get(`/bookings/${id}`) });
  const props = useQuery({ queryKey: ['properties'], queryFn: () => api.get<any[]>('/properties') });
  const b = q.data;
  const statement = useQuery({ queryKey: ['booking-statement', b?.property_id, b?.check_in?.slice(0, 7)], enabled: !!b,
    queryFn: () => api.get(`/reports/settlement?property_id=${b.property_id}&month=${b.check_in.slice(0, 7)}`) });
  const p = props.data?.find(x => x.id === b?.property_id);
  const cancel = async () => {
    if (savingCancel || !reason.trim()) return;
    setSavingCancel(true);
    try {
      await api.post(`/bookings/${id}/cancel`, { reason: reason.trim(), revision: b.revision ?? 0 });
      await qc.invalidateQueries();
      setCancelling(false);
      toast("Booking cancelled");
    } catch (error: any) { toast(error.message, "error"); }
    finally { setSavingCancel(false); }
  };
  return <View style={{ flex: 1 }}><Header back title="Booking details" />
    {q.isLoading ? <Loading /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={q.refetch} /> : <ScrollView contentContainerStyle={{ padding: 20, gap: 16, paddingBottom: 80 }}>
      {user?.role === 'admin' ? <Button title="Edit booking" onPress={() => router.push(`/booking/new?id=${id}`)} /> : null}
      {user?.role === 'admin' && b.status !== 'cancelled' ? <Card>
        <Button title={b.status === 'blocked' ? "Remove local block" : "Cancel booking"} variant="secondary" onPress={() => setCancelling(!cancelling)} />
        {cancelling ? <View style={{ gap: 12 }}>
          <Txt>This updates the local calendar. Update the OTA separately when necessary. Existing payments and completed cleaning history are retained.</Txt>
          <Input label="Cancellation reason" value={reason} onChangeText={setReason} multiline />
          <Button title="Confirm cancellation" disabled={!reason.trim()} loading={savingCancel} onPress={cancel} />
        </View> : null}
      </Card> : null}
      <Card><Txt v="subtitle">{b.guest_name}</Txt><Row label="Property" value={p?.name || ''} /><Row label={b.ota} value={b.status} />
        <Row label="Check-in" value={b.check_in} /><Row label="Check-out" value={b.check_out} /><Row label="Guests" value={String(b.guests)} />
        <Row label="Gross guest payment" value={inr(b.financials?.guest_total ?? b.amount)} />{!b.financials ? <Row label="OTA commission" value={inr(b.ota_commission)} /> : null}
        <Txt>{b.notes}</Txt></Card>
      <Card><BookingAmounts gross={b.amount} value={b.financials} commission={b.ota_commission || 0} readOnly ownerPercent={p?.owner_share_percent ?? 70} /></Card>
      {user?.role === "admin" ? <Button title="Guest IDs / upload link" variant="secondary" onPress={() => router.push(`/guests?booking_id=${id}`)} /> : null}
      <AdditionalRevenue booking={b} ownerPercent={p?.owner_share_percent ?? 70} />
      {statement.data ? <Card><Txt v="subtitle">Monthly payout · {b.check_in.slice(0, 7)}</Txt><Txt v="caption">Includes every booking and allocated expense for this month.</Txt>
        <Row label="Owner balance after all expenses" value={inr(statement.data.owner_before_tds ?? statement.data.owner_payout)} />
        <Row label="Owner TDS · monthly total" value={inr(statement.data.owner_tds || 0)} />
        <Row strong label="Owner payout after TDS" value={inr(statement.data.owner_payout)} />
        <Row label="Britsmaid net after expenses" value={inr(statement.data.britsmaid_net)} />
      </Card> : statement.isError ? <ErrorState message="Could not load the monthly payout" onRetry={statement.refetch} /> : null}
      <Button variant="secondary" title="View monthly statement and final payout" onPress={() => router.push(`/report/settlement?property_id=${b.property_id}&month=${b.check_in.slice(0, 7)}`)} />
    </ScrollView>}
  </View>;
}

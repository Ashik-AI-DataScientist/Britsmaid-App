import React from 'react';
import { ScrollView, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth';
import { BookingAmounts } from '@/src/components/BookingAmounts';
import { Button, Card, ErrorState, Header, Loading, Row, Txt } from '@/src/ui';
import { inr } from '@/src/format';

export default function BookingDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const q = useQuery({ queryKey: ['booking', id], queryFn: () => api.get(`/bookings/${id}`) });
  const props = useQuery({ queryKey: ['properties'], queryFn: () => api.get<any[]>('/properties') });
  const b = q.data;
  const statement = useQuery({ queryKey: ['booking-statement', b?.property_id, b?.check_in?.slice(0, 7)], enabled: !!b,
    queryFn: () => api.get(`/reports/settlement?property_id=${b.property_id}&month=${b.check_in.slice(0, 7)}`) });
  const p = props.data?.find(x => x.id === b?.property_id);
  return <View style={{ flex: 1 }}><Header back title="Booking details" />
    {q.isLoading ? <Loading /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={q.refetch} /> : <ScrollView contentContainerStyle={{ padding: 20, gap: 16, paddingBottom: 80 }}>
      {user?.role === 'admin' ? <Button title="Edit booking" onPress={() => router.push(`/booking/new?id=${id}`)} /> : null}
      <Card><Txt v="subtitle">{b.guest_name}</Txt><Row label="Property" value={p?.name || ''} /><Row label={b.ota} value={b.status} />
        <Row label="Check-in" value={b.check_in} /><Row label="Check-out" value={b.check_out} /><Row label="Guests" value={String(b.guests)} />
        <Row label="Gross guest payment" value={inr(b.financials?.guest_total ?? b.amount)} />{!b.financials ? <Row label="OTA commission" value={inr(b.ota_commission)} /> : null}
        <Txt>{b.notes}</Txt></Card>
      <Card><BookingAmounts gross={b.amount} value={b.financials} readOnly ownerPercent={p?.owner_share_percent ?? 70} /></Card>
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

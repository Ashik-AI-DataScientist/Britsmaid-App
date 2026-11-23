import React, { useState } from 'react';
import { Platform, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/src/auth';
import { api } from '@/src/api';
import { enableAdminPush, disableAdminPush } from '@/src/push';
import { Button, Card, ErrorState, Header, Loading, Txt, useToast } from '@/src/ui';

export default function Notifications() {
  const { user } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const q = useQuery({ queryKey: ['admin-activity'], enabled: user?.role === 'admin', queryFn: () => api.get<any[]>('/notifications'), refetchInterval: 15000 });
  const action = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); await q.refetch(); }
    catch (error: any) { toast(error.message, 'error'); }
    finally { setBusy(false); }
  };
  if (user?.role !== 'admin') return <View><Header back title="Activity" /><Txt>Admin access required.</Txt></View>;
  return <View style={{ flex: 1 }}><Header back title="Activity notifications" />
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
      {Platform.OS === 'web' ? <>
        <Button title="Enable phone notifications" loading={busy} onPress={() => action(enableAdminPush)} />
        <Button title="Disable notifications on this device" variant="secondary" disabled={busy} onPress={() => action(() => disableAdminPush())} />
        <Txt v="caption">On iPhone, open the app from your home screen to enable push. The activity inbox updates while you use the app.</Txt>
      </> : null}
      <Button title="Mark current activity read" variant="secondary" disabled={busy} onPress={() => action(() => api.post('/notifications/read'))} />
      {q.isLoading ? <Loading /> : q.isError ? <ErrorState onRetry={q.refetch} /> : !q.data?.length ? <Txt>No activity yet.</Txt> : q.data.map(item =>
        <Card key={item.id} onPress={() => { if (item.url !== '/notifications') router.push(item.url); }}>
          <Txt v="subtitle">{item.unread ? '● ' : ''}{item.title}</Txt>
          <Txt v="caption">{new Date(item.created_at).toLocaleString()}</Txt>
        </Card>)}
    </ScrollView>
  </View>;
}

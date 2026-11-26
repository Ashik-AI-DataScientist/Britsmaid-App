import { api } from './api';

// Refresh an existing worker without requesting notification permission again.
export async function refreshAdminPush() {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  try { await (await navigator.serviceWorker.getRegistration('/'))?.update(); } catch { /* Retry on a later visit. */ }
}

export async function enableAdminPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) throw new Error('Push is unavailable here. Use the activity inbox, or open the installed home-screen app.');
  if (await Notification.requestPermission() !== 'granted') throw new Error('Notifications are blocked in your browser settings. The activity inbox remains available.');
  const key = await api.get<{ public_key: string }>('/notifications/push-key');
  const registration = await navigator.serviceWorker.register('/admin-push.js');
  await navigator.serviceWorker.ready;
  const raw = atob(key.public_key.replace(/-/g, '+').replace(/_/g, '/'));
  const bytes = Uint8Array.from(raw, character => character.charCodeAt(0));
  const subscription = await registration.pushManager.getSubscription() ?? await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes });
  await api.post('/notifications/subscribe', subscription.toJSON());
}

export async function disableAdminPush(notifyServer = true) {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  const registration = await navigator.serviceWorker.getRegistration('/');
  const subscription = await registration?.pushManager.getSubscription();
  if (subscription) {
    if (notifyServer) await api.post('/notifications/unsubscribe', subscription.toJSON());
    await subscription.unsubscribe();
  }
}

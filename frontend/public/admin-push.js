/* global clients */
// Push only. Application screens and private API responses always use the network.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(clients.claim()));
self.addEventListener('push', event => {
  const message = event.data?.json() ?? {};
  event.waitUntil(self.registration.showNotification('Britsmaid activity', {
    body: message.body || 'New activity is available', tag: message.tag,
    icon: '/icons/britsmaid-192-v2.png', data: { url: '/notifications' }
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow('/notifications'));
});

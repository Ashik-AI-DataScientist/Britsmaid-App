/* global clients */
// Push only. Application screens and private API responses always use the network.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(clients.claim()));
function activityUrl(url) {
  return typeof url === 'string' && (/^\/(booking|cleaning|property|report|invoice)\/[a-f0-9]{24}$/.test(url)
    || /^\/guests\?booking_id=[a-f0-9]{24}$/.test(url) || ['/notifications', '/staff', '/issues', '/training'].includes(url)) ? url : '/notifications';
}
self.addEventListener('push', event => {
  const message = event.data?.json() ?? {};
  event.waitUntil(self.registration.showNotification(message.title || 'Britsmaid activity', {
    body: message.details || message.body || 'New activity is available', tag: message.tag,
    icon: '/icons/britsmaid-192-v2.png', data: { url: activityUrl(message.url) }
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow(activityUrl(event.notification.data?.url)));
});

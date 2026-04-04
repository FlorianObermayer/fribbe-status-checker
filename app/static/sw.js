self.addEventListener('push', event => {
    const data = event.data?.json() ?? {};
    const title = data.title || 'Fribbe Beach';
    const options = {
        body: data.body || 'Was ist los im Fribbe!',
        icon: '/static/images/favicon.ico',
        badge: '/static/images/favicon.ico',
        tag: 'fribbe-status-update',
        renotify: true,
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
            for (const client of clientList) {
                if (client.url.startsWith(self.location.origin) && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow('/');
            }
        })
    );
});

function getForDateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get('for_date');
}

function getNotificationIdsFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.getAll('n_ids');
}

function isNotificationsPreview() {
    const url = window.location.pathname
    if (url.includes("preview/notifications")) {
        return true;
    }
    return false;
}

async function enableNotification(notification_id) {
    const response = await fetch(`/api/notifications/${notification_id}`, {
        method: 'put',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ enabled: true })
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(`${errorData.detail || response.statusText}`);
    }
}

async function deleteNotification(notification_id) {
    const response = await fetch(`/api/notifications/${notification_id}`, {
        method: 'delete'
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(`${errorData.detail || response.statusText}`);
    }
}

async function deleteNotifications(notification_ids) {
    const query = notification_ids.map(id => `n_ids=${encodeURIComponent(id)}`).join('&');
    const response = await fetch(`/api/notifications?${query}`, {
        method: 'delete'
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(`${errorData.detail || response.statusText}`);
    }
}

async function copyTextToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.className = 'clipboard-textarea';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);

    if (!successful) {
        throw new Error('Copy command failed');
    }
}

let _toastTimeout = null;
function showToast(message, type = 'success') {
    let toast = document.getElementById('copy-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'copy-toast';
        toast.className = 'copy-toast';
        document.body.appendChild(toast);
    }

    toast.textContent = message;
    toast.classList.remove('success', 'error', 'visible');
    toast.classList.add(type);
    requestAnimationFrame(() => toast.classList.add('visible'));

    if (_toastTimeout) clearTimeout(_toastTimeout);
    _toastTimeout = setTimeout(() => toast.classList.remove('visible'), 1800);
}

async function updateStatus() {
    const dateTimeOptions = {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit'
    };

    const dateOptions = {
        weekday: 'long',
        day: 'numeric',
        month: 'short',
    };

    try {
        let forDate = getForDateFromUrl();
        let url = '/api/status';
        if (forDate && forDate !== 'today') {
            url += `?for_date=${encodeURIComponent(forDate)}`;
        }
        const response = await fetch(url);
        const data = await response.json();

        // Setze body based on presence state
        document.getElementById('status-body').className = `status-${data.presence.level}`;

        // Set correct traffic light based on presence state
        document.getElementById('red-light').classList.remove('active');
        document.getElementById('yellow-light').classList.remove('active');
        document.getElementById('green-light').classList.remove('active');

        if (data.presence.level === 'empty') {
            document.getElementById('red-light').classList.add('active');
        } else if (data.presence.level === 'few') {
            document.getElementById('yellow-light').classList.add('active');
        } else {
            document.getElementById('green-light').classList.add('active');
        }

        // Set status message
        document.getElementById('status-message').textContent = data.presence.message;

        document.querySelectorAll('.explanation-item').forEach(item => {
            item.classList.remove('active');
        });
        document.querySelector(`.explanation-item[data-status="${data.presence.level}"]`).classList.add('active');

        // --- OCCUPANCY DATA ---
        let occMsgElem = document.getElementById('occupancy-message');
        const occCard = document.getElementById('occupancy-card');
        if (Array.isArray(data.occupancy.messages) && data.occupancy.messages.length > 0) {
            occMsgElem.innerHTML = '<ul class="occupancy-list">' +
                data.occupancy.messages.map(msg => `<li>${msg}</li>`).join('') + '</ul>';
        } else {
            occMsgElem.textContent = 'Keine Belegungen oder Veranstaltungen!';
        }
        // Set Occupancy box header based on selected date / event type
        const occHeader = document.getElementById('occupancy-header');
        if (data.occupancy.source === 'event_calendar') {
            occHeader.textContent = forDate ? `Veranstaltungen (${new Date(data.occupancy.for_date).toLocaleDateString('de-DE', dateOptions)})` : 'Heutige Veranstaltungen';
        } else if (data.occupancy.source === 'weekly_plan') {
            occHeader.textContent = forDate ? `Belegungsplan (${new Date(data.occupancy.for_date).toLocaleDateString('de-DE', dateOptions)})` : 'Heutiger Belegungsplan';
        }
        // Mark box red with occupancy_type 'fully'
        if (data.occupancy.type === 'fully') {
            occCard.classList.add('occupancy-fully');
        } else {
            occCard.classList.remove('occupancy-fully');
        }

        // Combined Refresh Marker
        let combinedText = '';
        if (data.presence && data.presence.last_updated) {
            const p = new Date(data.presence.last_updated);
            combinedText += `Anwesenheit vom ${p.toLocaleDateString('de-DE', dateTimeOptions)}`;
        }
        if (data.occupancy && data.occupancy.last_updated) {
            const o = new Date(data.occupancy.last_updated);
            if (combinedText) combinedText += ' - ';
            combinedText += `Belegung vom ${o.toLocaleDateString('de-DE', dateTimeOptions)}`;
        }
        if (!combinedText) combinedText = 'Aktualisiert: Nie';
        document.getElementById('combined-updated-text').textContent = combinedText;

        setTrafficLightExplanation(data.presence.thresholds);
    } catch (error) {
        console.error('Fehler beim Laden des Status:', error);
        document.getElementById('status-message').textContent =
            'Fehler beim Laden des Status. Bitte versuche es später erneut.';
    }
}

function setTrafficLightExplanation(thresholds) {

    if (!thresholds
        || typeof thresholds.empty !== 'number'
        || typeof thresholds.few !== 'number'
        || typeof thresholds.many !== 'number'
    ) return;

    const red = document.getElementById('red-light');
    const explanationRed = document.getElementById('explanation-red')
    const redLegend = document.getElementById('legend-red-detail');

    const yellow = document.getElementById('yellow-light');
    const explanationYellow = document.getElementById('explanation-yellow');
    const yellowLegend = document.getElementById('legend-yellow-detail');

    const green = document.getElementById('green-light');
    const explanationGreen = document.getElementById('explanation-green');
    const greenLegend = document.getElementById('legend-green-detail');

    const redTooltip = `${thresholds.empty ? `${thresholds.empty} oder weniger` : thresholds.empty} aktive Geräte befinden sich im Fribbe-WiFi`;
    const yellowTooltip = `Zwischen ${thresholds.few} - ${thresholds.many} aktive Geräte befinden sich im Fribbe-WiFi`;
    const greenTooltip = `Mehr als ${thresholds.many} aktive Geräte befinden sich im Fribbe-WiFi`;

    if (red) red.title = redTooltip;
    if (explanationRed) explanationRed.title = redTooltip;
    if (redLegend) redLegend.textContent = redTooltip;

    if (yellow) yellow.title = yellowTooltip;
    if (explanationYellow) explanationYellow.title = yellowTooltip;
    if (yellowLegend) yellowLegend.textContent = yellowTooltip;
    if (green) green.title = greenTooltip;
    if (explanationGreen) explanationGreen.title = greenTooltip;
    if (greenLegend) greenLegend.textContent = greenTooltip;
}

function setupLegendToggle() {
    const toggle = document.querySelector('.legend-toggle');
    const overlay = document.querySelector('.legend-overlay');
    if (!toggle || !overlay) return;
    toggle.addEventListener('click', () => {
        const isOpen = overlay.classList.toggle('open');
        toggle.classList.toggle('open', isOpen);
    });
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.classList.remove('open');
            toggle.classList.remove('open');
        }
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            overlay.classList.remove('open');
            toggle.classList.remove('open');
        }
    });
}

let notificationDismissed = false;

function hashString(str) {
    let hash = 0, i, chr;
    if (str.length === 0) return hash;
    for (i = 0; i < str.length; i++) {
        chr = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + chr;
        hash |= 0;
    }
    return hash + "";
}

async function createNotificationsPreviewControls() {
    if (!isNotificationsPreview()) return;

    // Remove existing preview controls if any
    document.querySelectorAll('.preview-control').forEach(el => el.remove());

    const adminGroup = document.getElementById('admin-btn-group');
    if (!adminGroup) return;
    adminGroup.classList.add('admin-visible');

    // --- Filter select styled as pill ---
    const filterWrapper = document.createElement('div');
    filterWrapper.className = 'preview-control filter-wrapper';

    const filterSelect = document.createElement('select');
    filterSelect.className = 'filter-select preview-control';

    let filterOptions = [];
    try {
        const resp = await fetch('/api/notifications/filters');
        if (resp.ok) filterOptions = await resp.json();
    } catch { /* leave empty on error */ }

    filterOptions.forEach(({ value, label }) => {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        filterSelect.appendChild(opt);
    });
    const currentIds = getNotificationIdsFromUrl();
    if (currentIds.length === 1 && filterOptions.some(o => o.value === currentIds[0])) {
        filterSelect.value = currentIds[0];
    } else {
        filterSelect.value = 'all_active';
    }
    filterSelect.addEventListener('change', () => {
        const params = new URLSearchParams(window.location.search);
        params.delete('n_ids');
        params.append('n_ids', filterSelect.value);
        window.history.replaceState({}, '', window.location.pathname + '?' + params.toString());
        pollNotifications();
    });

    filterWrapper.appendChild(filterSelect);

    // --- Enable button ---
    const enableBtn = document.createElement('button');
    enableBtn.className = 'admin-btn preview-control';
    enableBtn.title = 'Aktivieren';
    enableBtn.dataset.tooltip = 'Aktivieren';
    enableBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>`;

    // --- Delete button ---
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'admin-btn preview-control';
    deleteBtn.title = 'Löschen';
    deleteBtn.dataset.tooltip = 'Löschen';
    deleteBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`;

    // Insert preview controls before the first existing admin-btn
    const firstAdminBtn = adminGroup.querySelector('.admin-btn:not(.preview-control)');
    adminGroup.insertBefore(filterWrapper, firstAdminBtn);
    adminGroup.insertBefore(enableBtn, firstAdminBtn);
    adminGroup.insertBefore(deleteBtn, firstAdminBtn);

    // --- Status toast helper ---
    const showStatus = (message, isError = false) => {
        showToast(message, isError ? 'error' : 'success');
    };

    enableBtn.addEventListener('click', async () => {
        const notificationIds = getNotificationIdsFromUrl();
        if (notificationIds.length !== 1 || notificationIds[0] === 'all_active') {
            showStatus('Keine spezifische Notification ID gefunden', true);
            return;
        }

        try {
            await enableNotification(notificationIds[0]);
            showStatus('Notification erfolgreich aktiviert');
            setTimeout(async () => {
                await pollNotifications();
            }, 1500);
        } catch (error) {
            showStatus(`Fehler: ${error.message}`, true);
        }
    });

    deleteBtn.addEventListener('click', async () => {
        const notificationIds = getNotificationIdsFromUrl();
        if (notificationIds.length === 0) {
            showStatus('Keine Notification IDs gefunden', true);
            return;
        }

        if (!confirm('Möchtest du diese Notification(s) wirklich löschen?')) return;

        try {
            await deleteNotifications(notificationIds);
            showStatus('Notification(s) erfolgreich gelöscht');
        } catch (error) {
            showStatus(`Fehler: ${error.message}`, true);
        }
    });
}

// Modify pollNotifications to call createNotificationControls
async function pollNotifications() {
    try {
        let notification_ids = getNotificationIdsFromUrl();

        if (notification_ids.length === 0) {
            notification_ids = ["all_active"];
        }

        // HACK: If specific notification is requested, show always
        if (notification_ids.length === 1 && notification_ids[0] !== "all_active") {
            localStorage.removeItem('notificationDismissedHash');
        }
        const query = notification_ids.join("&n_ids=")
        const resp = await fetch(`/api/notifications?n_ids=${query}`);
        if (!resp.ok) {
            throw Error(resp.statusText)
        }
        const html = await resp.text();
        const box = document.getElementById('notification-box');
        const htmlDiv = document.getElementById('notification-html');
        htmlDiv.innerHTML = html;
        const hash = hashString(htmlDiv.textContent);
        const lastNotificationHash = localStorage.getItem('notificationDismissedHash');
        if (html && html.trim()) {
            if (hash !== lastNotificationHash) {
                notificationDismissed = false;
                localStorage.removeItem('notificationDismissedHash');
            } else {
                notificationDismissed = true;
            }

            if (!notificationDismissed) {
                box.classList.remove('hidden');
            } else {
                box.classList.add('hidden');
            }
        } else {
            box.classList.add('hidden');
            localStorage.removeItem('notificationDismissedHash');
        }
        await createNotificationsPreviewControls();
        if (isNotificationsPreview()) {
            htmlDiv.querySelectorAll('[data-notification-id]').forEach(div => {
                div.classList.add('notification-preview-item');

                const container = document.createElement('div');
                container.className = 'notification-id-controls';

                const btn = document.createElement('button');
                btn.className = 'notification-id-btn';
                const nid = div.dataset.notificationId;
                const currentIds = getNotificationIdsFromUrl();
                const isSelected = currentIds.length === 1 && currentIds[0] === nid;
                btn.dataset.tooltip = nid;
                btn.title = nid;

                const filterIcon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>`;
                const copyIcon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;

                btn.innerHTML = isSelected ? copyIcon : filterIcon;
                if (isSelected) btn.classList.add('selected');

                btn.addEventListener('click', async () => {
                    if (isSelected) {
                        try {
                            await copyTextToClipboard(nid);
                            showToast('ID kopiert');
                        } catch {
                            showToast('Fehler beim Kopieren', 'error');
                        }
                    } else {
                        const params = new URLSearchParams(window.location.search);
                        params.delete('n_ids');
                        params.append('n_ids', nid);
                        window.history.replaceState({}, '', window.location.pathname + '?' + params.toString());
                        await pollNotifications();
                    }
                });

                container.appendChild(btn);
                div.prepend(container);
            });
        }
    } catch (e) {
        // ignore box on error
        document.getElementById('notification-box').classList.add('hidden');
        localStorage.removeItem('notificationDismissedHash');
        console.error(e)
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Date-Picker
    const dateInput = document.getElementById('for-date-picker');
    const todayBtn = document.getElementById('today-btn');
    const urlForDate = getForDateFromUrl();
    let today = new Date();
    let todayStr = today.getFullYear() + '-' +
        String(today.getMonth() + 1).padStart(2, '0') + '-' +
        String(today.getDate()).padStart(2, '0');
    if (dateInput) {
        dateInput.value = urlForDate || todayStr;
        dateInput.max = new Date(Date.now() + 1000 * 60 * 60 * 24 * 365).toISOString().slice(0, 10); // max 1 year in future
        dateInput.min = todayStr
        dateInput.addEventListener('change', (e) => {
            const val = e.target.value;
            const params = new URLSearchParams(window.location.search);
            if (val && val !== todayStr) {
                params.set('for_date', val);
            } else {
                params.delete('for_date');
            }
            const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
            window.history.replaceState({}, '', newUrl);
            updateStatus();
        });
    }
    if (todayBtn) {
        todayBtn.addEventListener('click', () => {
            if (dateInput) dateInput.value = todayStr;
            const params = new URLSearchParams(window.location.search);
            params.delete('for_date');
            const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
            window.history.replaceState({}, '', newUrl);
            updateStatus();
        });
    }
    updateStatus();
    setInterval(updateStatus, 30000); // Refresh status every 30 seconds
    setupLegendToggle();

    const signedIn = document.body.dataset.signedIn === 'true';
    const showAdminAuth = document.body.dataset.showAdminAuth === 'true';
    const bootstrapMode = document.body.dataset.bootstrapMode === 'true';

    const bootstrapBanner = document.getElementById('bootstrap-banner');
    if (bootstrapMode && bootstrapBanner) {
        bootstrapBanner.classList.remove('hidden');
    }
    const adminBtnGroup = document.getElementById('admin-btn-group');
    const signinBtn = document.getElementById('signin-btn');

    if (!signedIn && showAdminAuth && adminBtnGroup && signinBtn) {
        adminBtnGroup.classList.add('admin-visible');
        // Hide admin-only buttons, show only the sign-in button
        adminBtnGroup.querySelectorAll('.admin-btn:not(#signin-btn)').forEach(btn => btn.classList.add('hidden'));
    }

    if (signedIn && adminBtnGroup) {
        adminBtnGroup.classList.add('admin-visible');
        if (signinBtn) signinBtn.classList.add('hidden');

        const signoutBtn = document.getElementById('signout-btn');
        if (signoutBtn) {
            signoutBtn.addEventListener('click', async () => {
                await fetch('/signout', { method: 'POST' });
                window.location.href = '/';
            });
        }
    }

    const closeBtn = document.getElementById('notification-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            htmlDiv = document.getElementById('notification-html')
            hash = hashString(htmlDiv.textContent);

            document.getElementById('notification-box').classList.add('hidden');
            notificationDismissed = true;
            if (hash !== null) {
                localStorage.setItem('notificationDismissedHash', hash);
            }
        });
    }
    pollNotifications();
    setInterval(pollNotifications, 30000); // Poll for new notifications every 30 seconds

    initPushNotifications();
});

// ---- Web Push Notifications ----

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const output = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i++) output[i] = rawData.charCodeAt(i);
    return output;
}

function arrayBufferToBase64Url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    bytes.forEach(b => (binary += String.fromCharCode(b)));
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function setPushButtonState(state) {
    const row = document.getElementById('push-notify-row');
    const btn = document.getElementById('push-subscribe-btn');
    const label = document.getElementById('push-btn-label');
    if (!row || !btn || !label) return;

    row.classList.remove('hidden');
    btn.classList.remove('subscribed', 'denied');
    btn.disabled = false;

    if (state === 'subscribed') {
        btn.classList.add('subscribed');
        label.textContent = 'Benachrichtigung deaktivieren';
        btn.title = 'Push-Benachrichtigungen deaktivieren';
    } else if (state === 'denied') {
        btn.classList.add('denied');
        label.textContent = 'Benachrichtigungen blockiert';
        btn.title = 'Benachrichtigungen sind im Browser blockiert';
        btn.disabled = true;
    } else {
        label.textContent = 'Benachrichtigung aktivieren';
        btn.title = 'Push-Benachrichtigung, sobald die Meute ins Fribbe strömt!';
    }
}

async function initPushNotifications() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

    let vapidPublicKey;
    try {
        const resp = await fetch('/api/push/vapid-key');
        if (!resp.ok) return; // server not configured
        vapidPublicKey = (await resp.json()).public_key;
    } catch {
        return;
    }

    let swReg;
    try {
        swReg = await navigator.serviceWorker.register('/sw.js');
    } catch {
        return;
    }

    const permission = Notification.permission;
    if (permission === 'denied') {
        setPushButtonState('denied');
        return;
    }

    const existingSub = await swReg.pushManager.getSubscription();
    if (existingSub) {
        const auth = arrayBufferToBase64Url(existingSub.getKey('auth'));
        let serverKnows = false;
        try {
            const statusResp = await fetch(`/api/push/status?auth=${encodeURIComponent(auth)}`);
            serverKnows = statusResp.ok && (await statusResp.json()).subscribed;
        } catch { /* on network error assume server knows to avoid spurious re-registration */ }
        if (!serverKnows) {
            try {
                const reRegResp = await fetch('/api/push/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        endpoint: existingSub.endpoint,
                        p256dh: arrayBufferToBase64Url(existingSub.getKey('p256dh')),
                        auth,
                    }),
                });
                if (!reRegResp.ok) console.error('Push subscription re-registration failed:', reRegResp.status);
            } catch (e) {
                console.error('Push subscription re-registration failed:', e);
            }
        }
        setPushButtonState('subscribed');
    } else {
        setPushButtonState('unsubscribed');
    }

    const btn = document.getElementById('push-subscribe-btn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        const currentSub = await swReg.pushManager.getSubscription();
        if (currentSub) {
            // Unsubscribe
            try {
                const auth = arrayBufferToBase64Url(currentSub.getKey('auth'));
                await currentSub.unsubscribe();
                const resp = await fetch('/api/push/unsubscribe', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ auth }),
                });
                if (!resp.ok) {
                    throw new Error(`Unsubscribe request failed with status ${resp.status}`);
                }
                setPushButtonState('unsubscribed');
            } catch (e) {
                console.error('Unsubscribe failed:', e);
                showToast('Fehler beim Deaktivieren', 'error');
            }
        } else {
            // Subscribe
            try {
                const sub = await swReg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
                });
                const resp = await fetch('/api/push/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        endpoint: sub.endpoint,
                        p256dh: arrayBufferToBase64Url(sub.getKey('p256dh')),
                        auth: arrayBufferToBase64Url(sub.getKey('auth')),
                    }),
                });
                if (!resp.ok) {
                    await sub.unsubscribe();
                    throw new Error(`Subscribe request failed with status ${resp.status}`);
                }
                setPushButtonState('subscribed');
                showToast('Benachrichtigungen aktiviert!');
            } catch (e) {
                if (Notification.permission === 'denied') {
                    setPushButtonState('denied');
                } else {
                    console.error('Subscribe failed:', e);
                    showToast('Fehler beim Aktivieren', 'error');
                }
            }
        }
    });
}
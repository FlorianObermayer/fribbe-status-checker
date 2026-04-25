// Globals from classic scripts loaded before this module (csrf.js, toast.js,
// clipboard.js — see base.html). ES modules don't see the classic-script scope.
const { showToast, withCsrfHeaders, copyTextToClipboard } = /** @type {any} */ (window);

function getForDateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get('for_date');
}

function getNotificationIdsFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.getAll('n_ids');
}

// Page-config URLs injected via data-* attributes on <body> by the Jinja template.
const _cfg = document.body.dataset;
const NOTIFICATIONS_URL = _cfg.notificationsUrl;
const STATUS_URL = _cfg.statusUrl;
const API_PUSH_VAPID_KEY_URL = _cfg.pushVapidKeyUrl;
const API_PUSH_STATUS_URL = _cfg.pushStatusUrl;
const API_PUSH_SUBSCRIBE_URL = _cfg.pushSubscribeUrl;
const API_PUSH_UNSUBSCRIBE_URL = _cfg.pushUnsubscribeUrl;
const API_PUSH_TOPICS_URL = _cfg.pushTopicsUrl;

async function updateStatus() {
    try {
        let forDate = getForDateFromUrl();
        let url = STATUS_URL;
        if (forDate && forDate !== 'today') {
            url += `?for_date=${encodeURIComponent(forDate)}`;
        }
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(response.statusText);
        }
        const html = await response.text();
        const container = document.getElementById('status-content-container');
        container.innerHTML = html;

        // Read data attributes from the server-rendered fragment
        const content = document.getElementById('status-content');
        const level = content?.dataset.level;
        const thresholdEmpty = content?.dataset.thresholdEmpty;
        const thresholdFew = content?.dataset.thresholdFew;
        const thresholdMany = content?.dataset.thresholdMany;

        // Update body class based on presence level
        document.getElementById('status-body').className = `status-${level}`;

        // Set correct traffic light
        document.getElementById('red-light').classList.remove('active');
        document.getElementById('yellow-light').classList.remove('active');
        document.getElementById('green-light').classList.remove('active');
        if (level === 'empty') {
            document.getElementById('red-light').classList.add('active');
        } else if (level === 'few') {
            document.getElementById('yellow-light').classList.add('active');
        } else {
            document.getElementById('green-light').classList.add('active');
        }

        // Highlight matching explanation item
        document.querySelectorAll('.explanation-item').forEach(item => {
            item.classList.remove('active');
        });
        const activeItem = document.querySelector(`.explanation-item[data-status="${level}"]`);
        if (activeItem) activeItem.classList.add('active');

        // Update legend tooltips from data attributes
        if (thresholdEmpty && thresholdFew && thresholdMany) {
            setTrafficLightExplanation({
                empty: Number(thresholdEmpty),
                few: Number(thresholdFew),
                many: Number(thresholdMany),
            });
        }

        // Re-attach date picker listeners
        setupDatePicker();
    } catch (error) {
        console.error('Fehler beim Laden des Status:', error);
        const msg = document.getElementById('status-message');
        if (msg) msg.textContent = 'Fehler beim Laden des Status. Bitte versuche es später erneut.';
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

export const NOTIFICATION_DISMISSED_KEY = 'notificationDismissedHash';

export function hashString(str) {
    let hash = 0, i, chr;
    if (str.length === 0) return hash + '';
    for (i = 0; i < str.length; i++) {
        chr = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + chr;
        hash |= 0;
    }
    return hash + '';
}

// Decide whether to show the notification based on the latest poll response
// and the previously stored "dismissed" hash. Exported for unit tests.
export function computeNotificationState(html, textContent, storedHash) {
    if (!html || !html.trim()) {
        // Empty response — keep the stored hash so a re-appearing notification
        // that was already dismissed stays hidden.
        return { dismissed: true, clearHash: false };
    }
    const hash = hashString(textContent);
    if (hash !== storedHash) {
        return { dismissed: false, clearHash: true };
    }
    return { dismissed: true, clearHash: false };
}

// Poll and display notifications
async function pollNotifications() {
    try {
        let notification_ids = getNotificationIdsFromUrl();

        if (notification_ids.length === 0) {
            notification_ids = ["all_active"];
        }

        // HACK: If specific notification is requested, show always
        if (notification_ids.length === 1 && notification_ids[0] !== "all_active") {
            localStorage.removeItem(NOTIFICATION_DISMISSED_KEY);
        }
        const query = notification_ids.join("&n_ids=")
        const url = `${NOTIFICATIONS_URL}?n_ids=${query}`;
        const resp = await fetch(url);
        if (!resp.ok) {
            throw Error(resp.statusText)
        }
        const html = await resp.text();
        const box = document.getElementById('notification-box');
        const htmlDiv = document.getElementById('notification-html');
        htmlDiv.innerHTML = html;
        const { dismissed, clearHash } = computeNotificationState(
            html, htmlDiv.textContent, localStorage.getItem(NOTIFICATION_DISMISSED_KEY));
        if (clearHash) {
            localStorage.removeItem(NOTIFICATION_DISMISSED_KEY);
        }
        notificationDismissed = dismissed;
        box.classList.toggle('hidden', notificationDismissed);
    } catch (e) {
        // ignore box on error
        document.getElementById('notification-box').classList.add('hidden');
        console.error(e)
    }
}

function setupDatePicker() {
    const dateInput = document.getElementById('for-date-picker');
    const todayBtn = document.getElementById('today-btn');
    let today = new Date();
    let todayStr = today.getFullYear() + '-' +
        String(today.getMonth() + 1).padStart(2, '0') + '-' +
        String(today.getDate()).padStart(2, '0');
    if (dateInput) {
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
}

document.addEventListener('DOMContentLoaded', () => {
    setupDatePicker();
    updateStatus();
    setInterval(updateStatus, 30000); // Refresh status every 30 seconds
    setupLegendToggle();

    const closeBtn = document.getElementById('notification-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            const htmlDiv = document.getElementById('notification-html')
            const hash = hashString(htmlDiv.textContent);

            document.getElementById('notification-box').classList.add('hidden');
            notificationDismissed = true;
            if (hash !== null) {
                localStorage.setItem(NOTIFICATION_DISMISSED_KEY, hash);
            }
        });
    }
    pollNotifications();
    setInterval(pollNotifications, 30000); // Poll for new notifications every 30 seconds

    // Clipboard copy for server-rendered notification ID buttons on preview page
    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('.copy-nid-btn');
        if (!btn) return;
        try {
            await copyTextToClipboard(btn.dataset.nid);
            showToast('ID kopiert');
        } catch {
            showToast('Fehler beim Kopieren', 'error');
        }
    });

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
    const caret = document.getElementById('push-caret-icon');
    const panel = document.getElementById('push-topic-panel');
    if (!row || !btn || !label) return;

    row.classList.remove('hidden');
    btn.classList.remove('subscribed', 'denied', 'loading');
    btn.disabled = false;
    if (caret) { caret.classList.add('hidden'); caret.classList.remove('open'); }
    if (panel) panel.classList.add('hidden');

    if (state === 'loading') {
        btn.classList.add('loading');
        btn.disabled = true;
        label.textContent = 'Bitte warten...';
        btn.title = '';
        return;
    }

    if (state === 'subscribed') {
        btn.classList.add('subscribed');
        label.textContent = 'Benachrichtigungen aktiv';
        btn.title = 'Einstellungen';
        if (caret) caret.classList.remove('hidden');
    } else if (state === 'denied') {
        btn.classList.add('denied');
        label.textContent = 'Benachrichtigungen blockiert';
        btn.title = 'Benachrichtigungen sind im Browser blockiert';
        btn.disabled = true;
    } else {
        label.textContent = 'Benachrichtigungen aktivieren';
        btn.title = 'Push-Benachrichtigungen, sobald es was Neues gibt oder die Meute ins Fribbe strömt!';
    }
}

function togglePushPanel() {
    const panel = document.getElementById('push-topic-panel');
    const caret = document.getElementById('push-caret-icon');
    if (!panel) return;
    const isOpen = !panel.classList.contains('hidden');
    panel.classList.toggle('hidden', isOpen);
    if (caret) caret.classList.toggle('open', !isOpen);
}

function setTopicCheckboxes(topics) {
    document.querySelectorAll('.push-topic-checkbox').forEach(cb => {
        cb.checked = topics.includes(cb.value);
    });
}

async function initPushNotifications() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        // On iOS Safari, PushManager is only available in standalone (home screen) mode.
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
            (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
        const isStandalone = window.matchMedia('(display-mode: standalone)').matches ||
            navigator.standalone === true;
        if (isIOS && !isStandalone) {
            const hint = document.getElementById('push-ios-hint');
            if (hint) hint.classList.remove('hidden');
        }
        return;
    }

    let vapidPublicKey;
    try {
        const resp = await fetch(API_PUSH_VAPID_KEY_URL);
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
        let currentTopics = ['notifications', 'presence'];
        try {
            const statusResp = await fetch(API_PUSH_STATUS_URL, {
                method: 'POST',
                headers: withCsrfHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ auth }),
            });
            if (statusResp.ok) {
                const statusData = await statusResp.json();
                serverKnows = statusData.subscribed;
                if (serverKnows) currentTopics = statusData.topics ?? currentTopics;
            }
        } catch {
            serverKnows = true; // on network error assume server knows to avoid spurious re-registration
        }
        if (!serverKnows) {
            let reRegOk = false;
            try {
                const reRegResp = await fetch(API_PUSH_SUBSCRIBE_URL, {
                    method: 'POST',
                    headers: withCsrfHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({
                        endpoint: existingSub.endpoint,
                        p256dh: arrayBufferToBase64Url(existingSub.getKey('p256dh')),
                        auth,
                        topics: ['notifications', 'presence'],
                    }),
                });
                reRegOk = reRegResp.ok;
                if (!reRegOk) console.error('Push subscription re-registration failed:', reRegResp.status);
            } catch (e) {
                console.error('Push subscription re-registration failed:', e);
            }
            if (!reRegOk) {
                setPushButtonState('unsubscribed');
                showToast('Fehler beim Aktivieren', 'error');
                return;
            }
        }
        setPushButtonState('subscribed');
        setTopicCheckboxes(currentTopics);
    } else {
        setPushButtonState('unsubscribed');
    }

    const btn = document.getElementById('push-subscribe-btn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        let currentSub;
        try {
            currentSub = await swReg.pushManager.getSubscription();
        } catch (e) {
            console.error('Failed to get push subscription:', e);
            showToast('Fehler beim Laden des Benachrichtigungsstatus', 'error');
            return;
        }
        if (currentSub) {
            togglePushPanel();
        } else {
            // Subscribe
            setPushButtonState('loading');
            try {
                const sub = await swReg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
                });
                const resp = await fetch(API_PUSH_SUBSCRIBE_URL, {
                    method: 'POST',
                    headers: withCsrfHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({
                        endpoint: sub.endpoint,
                        p256dh: arrayBufferToBase64Url(sub.getKey('p256dh')),
                        auth: arrayBufferToBase64Url(sub.getKey('auth')),
                        topics: ['notifications', 'presence'],
                    }),
                });
                if (!resp.ok) {
                    await sub.unsubscribe();
                    throw new Error(`Subscribe request failed with status ${resp.status}`);
                }
                setPushButtonState('subscribed');
                setTopicCheckboxes(['notifications', 'presence']);
                showToast('Alle Push-Benachrichtigungen aktiviert!');
            } catch (e) {
                if (Notification.permission === 'denied') {
                    setPushButtonState('denied');
                } else {
                    console.error('Subscribe failed:', e);
                    setPushButtonState('unsubscribed');
                    showToast('Fehler beim Aktivieren', 'error');
                }
            }
        }
    });

    // Topic checkboxes: patch topics on change, prevent deselecting all
    document.querySelectorAll('.push-topic-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', async () => {
            const currentSub = await swReg.pushManager.getSubscription().catch(() => null);
            if (!currentSub) return;
            const auth = arrayBufferToBase64Url(currentSub.getKey('auth'));
            const checked = [...document.querySelectorAll('.push-topic-checkbox:checked')].map(el => el.value);
            if (checked.length === 0) {
                checkbox.checked = true; // prevent deselecting all
                return;
            }
            const label = checkbox.closest('label')?.textContent?.trim() ?? checkbox.value;
            try {
                const resp = await fetch(API_PUSH_TOPICS_URL, {
                    method: 'PATCH',
                    headers: withCsrfHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({ auth, topics: checked }),
                });
                if (!resp.ok) throw new Error(`PATCH /api/push/topics failed with status ${resp.status}`);
                showToast(`Push-Benachrichtigungen für '${label}' ${checkbox.checked ? 'aktiviert' : 'deaktiviert'}`);
            } catch (e) {
                console.error('Failed to update push topics:', e);
                checkbox.checked = !checkbox.checked; // revert on error
                showToast('Fehler beim Speichern', 'error');
            }
        });
    });

    // Unsubscribe button inside topic panel
    const unsubBtn = document.getElementById('push-unsubscribe-btn');
    if (unsubBtn) {
        unsubBtn.addEventListener('click', async () => {
            setPushButtonState('loading');
            try {
                const currentSub = await swReg.pushManager.getSubscription();
                if (currentSub) {
                    const auth = arrayBufferToBase64Url(currentSub.getKey('auth'));
                    const resp = await fetch(API_PUSH_UNSUBSCRIBE_URL, {
                        method: 'DELETE',
                        headers: withCsrfHeaders({ 'Content-Type': 'application/json' }),
                        body: JSON.stringify({ auth }),
                    });
                    if (!resp.ok) throw new Error(`Unsubscribe request failed with status ${resp.status}`);
                    const unsubscribed = await currentSub.unsubscribe();
                    if (!unsubscribed) throw new Error('Browser unsubscribe returned false');
                }
                setPushButtonState('unsubscribed');
                showToast('Alle Push-Benachrichtigungen deaktiviert!');
            } catch (e) {
                console.error('Unsubscribe failed:', e);
                setPushButtonState('subscribed');
                showToast('Fehler beim Deaktivieren', 'error');
            }
        });
    }

    // Close panel when clicking outside the wrapper
    document.addEventListener('click', e => {
        const wrapper = document.getElementById('push-btn-wrapper');
        const panel = document.getElementById('push-topic-panel');
        const caret = document.getElementById('push-caret-icon');
        if (wrapper && panel && !wrapper.contains(e.target) && !panel.classList.contains('hidden')) {
            panel.classList.add('hidden');
            if (caret) caret.classList.remove('open');
        }
    });
}
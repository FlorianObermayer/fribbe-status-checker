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
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    textArea.style.top = '-9999px';
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
            occCard.style.display = '';
            occMsgElem.innerHTML = '<ul style="margin:0; padding-left:24px;text-align:left;">' +
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

    // Remove existing controls if any
    const existingControls = document.querySelector('.notification-controls');
    if (existingControls) existingControls.remove();

    const controls = document.createElement('div');
    controls.className = 'notification-controls';

    const filterSelect = document.createElement('select');
    filterSelect.className = 'filter-select';

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
    // Set current selection from URL, defaulting to all_active
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

    const enableBtn = document.createElement('button');
    enableBtn.className = 'enable-btn';
    enableBtn.textContent = 'Aktivieren';

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'delete-btn';
    deleteBtn.textContent = 'Löschen';

    controls.appendChild(filterSelect);
    controls.appendChild(enableBtn);
    controls.appendChild(deleteBtn);

    document.body.appendChild(controls);

    let statusTimeout;

    const showStatus = (message, isError = false) => {
        const statusMsg = document.createElement('div');
        statusMsg.className = `status-message ${isError ? 'error' : 'success'}`;
        statusMsg.textContent = message;
        controls.appendChild(statusMsg);

        if (statusTimeout) clearTimeout(statusTimeout);
        statusTimeout = setTimeout(() => {
            statusMsg.remove();
        }, 3000);
    };

    // Add click handlers
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
                await pollNotifications();  // Refresh the preview
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

        console.log("notification_ids:", notification_ids)

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
                box.style.display = '';
            } else {
                box.style.display = 'none';
            }
        } else {
            box.style.display = 'none';
            localStorage.removeItem('notificationDismissedHash');
        }
        await createNotificationsPreviewControls();
        if (isNotificationsPreview()) {
            htmlDiv.querySelectorAll('[data-notification-id]').forEach(div => {
                div.style.position = 'relative';

                const container = document.createElement('div');
                container.className = 'notification-id-controls';

                const badge = document.createElement('span');
                badge.className = 'notification-id-badge';
                badge.textContent = div.dataset.notificationId;
                const nid = div.dataset.notificationId;
                const currentIds = getNotificationIdsFromUrl();
                const isSelected = currentIds.length === 1 && currentIds[0] === nid;
                badge.title = isSelected ? 'Klicken zum Kopieren' : 'Klicken zum Auswählen';
                if (isSelected) badge.classList.add('selected');
                badge.addEventListener('click', async () => {
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

                container.appendChild(badge);
                div.prepend(container);
            });
        }
    } catch (e) {
        // ignore box on error
        document.getElementById('notification-box').style.display = 'none';
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
        dateInput.max = new Date(Date.now() + 1000 * 60 * 60 * 24 * 365).toISOString().slice(0, 10); // max 1 Jahr in Zukunft
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

    const closeBtn = document.getElementById('notification-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            htmlDiv = document.getElementById('notification-html')
            hash = hashString(htmlDiv.textContent);

            document.getElementById('notification-box').style.display = 'none';
            notificationDismissed = true;
            if (hash !== null) {
                localStorage.setItem('notificationDismissedHash', hash);
            }
        });
    }
    pollNotifications();
    setInterval(pollNotifications, 30000); // Poll for new notifications every 30 seconds
});
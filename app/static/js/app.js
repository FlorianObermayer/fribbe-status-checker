
function getForDateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get('for_date');
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

        // Tooltip logic: set native title attributes for traffic lights
        setTrafficLightTooltips(data.presence.thresholds);
    } catch (error) {
        console.error('Fehler beim Laden des Status:', error);
        document.getElementById('status-message').textContent =
            'Fehler beim Laden des Status. Bitte versuche es später erneut.';
    }
}

function setTrafficLightTooltips(thresholds) {

    const red = document.getElementById('red-light');
    const explanationRed = document.getElementById('explanation-red')
    const yellow = document.getElementById('yellow-light');
    const explanationYellow = document.getElementById('explanation-yellow');
    const green = document.getElementById('green-light');
    const explanationGreen = document.getElementById('explanation-green');

    if (!thresholds
        || typeof thresholds.empty !== 'number'
        || typeof thresholds.few !== 'number'
        || typeof thresholds.many !== 'number'
    ) return;

    const redTooltip = `${thresholds.empty ? `${thresholds.empty} oder weniger` : thresholds.empty} Geräte befinden sich im Fribbe-WiFi`;
    const yellowTooltip = `Zwischen ${thresholds.few} - ${thresholds.many} aktive Geräte befinden sich im Fribbe-WiFi`;
    const greenTooltip = `Mehr als ${thresholds.many} aktive Geräte befinden sich im Fribbe-WiFi`;

    if (red) {
        red.title = redTooltip
    }
    if (explanationRed) {
        explanationRed.title = redTooltip
    }

    if (yellow) {
        yellow.title = yellowTooltip
    }
    if (explanationYellow) {
        explanationYellow.title = yellowTooltip
    }

    if (green) {
        green.title = greenTooltip
    }

    if (explanationGreen) {
        explanationGreen.title = greenTooltip;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Date-Picker
    const dateInput = document.getElementById('for-date-picker');
    const todayBtn = document.getElementById('today-btn');
    const urlForDate = getForDateFromUrl();
    let todayStr = new Date().toISOString().slice(0, 10);
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
});
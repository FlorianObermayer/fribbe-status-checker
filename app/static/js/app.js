function getForDateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get('for_date');
}

function setTooltipThresholds(thresholds) {
    // thresholds: {empty: X, few: Y, many: Z}
    // Ampel
    document.querySelector('#red-light .tooltip').setAttribute('data-tooltip', `Weniger als ${thresholds.few} Geräte online (Ampel ist rot)`);
    document.querySelector('#yellow-light .tooltip').setAttribute('data-tooltip', `Zwischen ${thresholds.few} und ${thresholds.many} Geräte online (Ampel ist gelb)`);
    document.querySelector('#green-light .tooltip').setAttribute('data-tooltip', `Mehr als ${thresholds.many} Geräte online (Ampel ist grün)`);
    // Legende
    document.querySelector('.explanation-item[data-status="empty"] .tooltip').setAttribute('data-tooltip', `Weniger als ${thresholds.few} Geräte online: Ampel ist rot`);
    document.querySelector('.explanation-item[data-status="few"] .tooltip').setAttribute('data-tooltip', `Zwischen ${thresholds.few} und ${thresholds.many} Geräte online: Ampel ist gelb`);
    document.querySelector('.explanation-item[data-status="many"] .tooltip').setAttribute('data-tooltip', `Mehr als ${thresholds.many} Geräte online: Ampel ist grün`);
}

// Touch-Unterstützung für Tooltips
function enableTouchTooltips() {
    document.querySelectorAll('.tooltip').forEach(el => {
        el.addEventListener('touchstart', function (e) {
            e.stopPropagation();
            document.querySelectorAll('.tooltip').forEach(t => t.classList.remove('show-tooltip'));
            this.classList.add('show-tooltip');
        });
    });
    document.body.addEventListener('touchstart', function () {
        document.querySelectorAll('.tooltip').forEach(t => t.classList.remove('show-tooltip'));
    });
}

function enableDynamicTooltipPositioning() {
    // Für Mouse Hover
    document.querySelectorAll('.tooltip').forEach(el => {
        el.addEventListener('mousemove', function (e) {
            if (!this.hasAttribute('data-tooltip')) return;
            const tooltip = this;
            const tooltipBox = tooltip;
            const tooltipText = tooltip.getAttribute('data-tooltip');
            // Temporär Tooltip anzeigen, um Größe zu messen
            tooltip.classList.add('show-tooltip');
            setTimeout(() => {
                const after = window.getComputedStyle(tooltip, '::after');
                // Position berechnen
                const mouseX = e.clientX;
                const mouseY = e.clientY;
                // Tooltip-Box nach rechts unten, aber im Viewport
                const boxWidth = 220;
                const boxHeight = 60;
                let left = mouseX + 16;
                let top = mouseY + 8;
                if (left + boxWidth > window.innerWidth) left = window.innerWidth - boxWidth - 8;
                if (top + boxHeight > window.innerHeight) top = window.innerHeight - boxHeight - 8;
                tooltip.style.setProperty('--tooltip-x', left + 'px');
                tooltip.style.setProperty('--tooltip-y', top + 'px');
            }, 0);
        });
        el.addEventListener('mouseleave', function () {
            this.classList.remove('show-tooltip');
        });
    });
    // Für Touch
    document.querySelectorAll('.tooltip').forEach(el => {
        el.addEventListener('touchstart', function (e) {
            e.stopPropagation();
            document.querySelectorAll('.tooltip').forEach(t => t.classList.remove('show-tooltip'));
            this.classList.add('show-tooltip');
            // Tooltip unter das Element setzen
            const rect = this.getBoundingClientRect();
            let left = rect.left + rect.width / 2 - 110;
            let top = rect.bottom + 8;
            if (left < 0) left = 8;
            if (left + 220 > window.innerWidth) left = window.innerWidth - 220;
            if (top + 60 > window.innerHeight) top = window.innerHeight - 60;
            this.style.setProperty('--tooltip-x', left + 'px');
            this.style.setProperty('--tooltip-y', top + 'px');
        });
    });
    document.body.addEventListener('touchstart', function () {
        document.querySelectorAll('.tooltip').forEach(t => t.classList.remove('show-tooltip'));
    });
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

        // Setze Tooltips für Schwellenwerte
        if (data.presence && data.presence.thresholds) {
            setTooltipThresholds(data.presence.thresholds);
        }

    } catch (error) {
        console.error('Fehler beim Laden des Status:', error);
        document.getElementById('status-message').textContent =
            'Fehler beim Laden des Status. Bitte versuche es später erneut.';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    enableTouchTooltips();
    enableDynamicTooltipPositioning();
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
    setTimeout(() => {
        window.scrollTo(1, 0)
        window.scrollTo(0, 0)
    }, 50); // Hack: Fixes initial weird scrolling bug
});
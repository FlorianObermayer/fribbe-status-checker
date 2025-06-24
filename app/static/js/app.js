// Funktion zum Auslesen des for_date aus der URL
function getForDateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get('for_date');
}


// Funktion zum Aktualisieren des Status
async function updateStatus() {

    const dateTimeOptions = {
        //weekday: 'short',
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
        
        // Setze Body-Klasse basierend auf Status
        document.getElementById('status-body').className = `status-${data.presence.level}`;
        
        // Aktiviere das richtige Licht
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
        
        // Setze Statusnachricht
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
            occCard.style.display = 'none';
            occMsgElem.textContent = '-';
        }
        // Header dynamisch setzen
        const occHeader = document.getElementById('occupancy-header');
        if (data.occupancy.source === 'event_calendar') {
            occHeader.textContent = forDate ? `Veranstaltungen (${new Date(data.occupancy.for_date).toLocaleDateString('de-DE', dateOptions)})` : 'Heutige Veranstaltungen';
        } else if (data.occupancy.source === 'weekly_plan') {
            occHeader.textContent = forDate ? `Belegungsplan (${new Date(data.occupancy.for_date).toLocaleDateString('de-DE', dateOptions)})` : 'Heutiger Belegungsplan';
        }
        // Rötliche Färbung bei occupancy_type 'fully'
        if (data.occupancy.type === 'fully') {
            occCard.classList.add('occupancy-fully');
        } else {
            occCard.classList.remove('occupancy-fully');
        }

        // Kombinierter Aktualisierungsmarker
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

    } catch (error) {
        console.error('Fehler beim Laden des Status:', error);
        document.getElementById('status-message').textContent = 
            'Fehler beim Laden des Status. Bitte versuche es später erneut.';
    }
}

// Status beim Laden aktualisieren und alle 30 Sekunden neu laden
document.addEventListener('DOMContentLoaded', () => {
    updateStatus();
    setInterval(updateStatus, 30000); // Alle 30 Sekunden aktualisieren
});
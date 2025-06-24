// Funktion zum Aktualisieren des Status
async function updateStatus() {
    try {
        const response = await fetch('/api/status');
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

        // Formatieren des Datums
        const lastUpdated = new Date(data.presence.last_updated);
        const options = { 
            weekday: 'long', 
            day: 'numeric', 
            month: 'long', 
            hour: '2-digit', 
            minute: '2-digit' 
        };
        document.getElementById('timestamp').textContent = 
            lastUpdated.toLocaleDateString('de-DE', options);
        
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

// Load Markdown Editor
function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : '';
}


function withCsrfHeaders(headers = {}) {
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        return headers;
    }
    return { ...headers, 'X-CSRF-Token': csrfToken };
}


const easyMDE = new EasyMDE({
    element: document.getElementById('message'),
    autosave: {
        enabled: true,
        timeFormat: "locale: de-DE, format: HH:mm",
        uniqueId: "unique-id",
    },
    autoDownloadFontAwesome: true,
    previewImagesInEditor: true,
    spellChecker: false,
    toolbar: false,
    forceSync: true,
});

document.getElementById('submitBtn').addEventListener('click', async function () {
    const message = document.getElementById('message').value;
    const validFrom = document.getElementById('validFrom').value;
    const validUntil = document.getElementById('validUntil').value;
    const enabled = false;

    const resultDiv = document.getElementById('result');
    resultDiv.className = '';
    resultDiv.textContent = '';

    if (!message) {
        resultDiv.textContent = 'Nachricht is ein Pflichtfeld';
        resultDiv.classList.add('error');
        return;
    }

    const payload = {
        message,
        enabled
    };

    if (validFrom) payload.valid_from = new Date(validFrom).toISOString();
    if (validUntil) payload.valid_until = new Date(validUntil).toISOString();

    try {
        const response = await fetch('/api/notifications', {
            method: 'POST',
            headers: withCsrfHeaders({
                'Content-Type': 'application/json',
            }),
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            if (response.ok) {
                const result = await response.json();
                const notification_id = result["notification_id"];
                resultDiv.innerHTML = `
    <div class="success-message">
        Nachricht erfolgreich erstellt (nur als Vorschau)!
        <a href="${window.location.origin}/preview/notifications?n_ids=${notification_id}" 
           target="_blank" 
           class="preview-button">
           <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
           Vorschau öffnen
        </a>
    </div>`;
                resultDiv.classList.add('success');
            }
        } else {
            const errorData = await response.json();
            resultDiv.textContent = `Error: ${errorData.detail || response.statusText}`;
            resultDiv.classList.add('error');
        }
    } catch (error) {
        resultDiv.textContent = `Network error: ${error.message}`;
        resultDiv.classList.add('error');
    }
});

// Set default datetime values to now and 1 hour from now
const now = new Date();
const today = new Date(now)
today.setSeconds(0);
today.setMinutes(0);
today.setHours(0);
const endOfDay = new Date(now);
endOfDay.setSeconds(59);
endOfDay.setMinutes(59);
endOfDay.setHours(23);

document.getElementById('validFrom').value = formatDateTimeLocal(today);
document.getElementById('validUntil').value = formatDateTimeLocal(endOfDay);

function formatDateTimeLocal(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    return `${year}-${month}-${day}T${hours}:${minutes}`;
}
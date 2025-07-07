
// Load Markdown Editor
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

document.addEventListener('DOMContentLoaded', () => {
    // restore api key
    const savedApiKey = localStorage.getItem('notification_api_key');
    if (savedApiKey) {
        document.getElementById('apiKey').value = savedApiKey;
    }
});

document.getElementById('submitBtn').addEventListener('click', async function () {
    const rememberMe = document.getElementById('rememberMe').checked;

    const apiKey = document.getElementById('apiKey').value;
    const message = document.getElementById('message').value;
    const validFrom = document.getElementById('validFrom').value;
    const validUntil = document.getElementById('validUntil').value;
    const enabled = document.getElementById('enabled').checked;

    const resultDiv = document.getElementById('result');
    resultDiv.className = '';
    resultDiv.textContent = '';

    if (rememberMe && apiKey) {
        localStorage.setItem('notification_api_key', apiKey);
    } else {
        localStorage.removeItem('notification_api_key');
    }

    if (!apiKey) {
        resultDiv.textContent = 'API Schlüssel ist ein Pflichtfeld';
        resultDiv.classList.add('error');
        return;
    }

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
            headers: {
                'Content-Type': 'application/json',
                'api_key': apiKey
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            resultDiv.textContent = 'Nachricht erfolgreich erstellt!';
            resultDiv.classList.add('success');
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
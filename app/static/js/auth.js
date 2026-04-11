(function auth() {
    const next = document.body.dataset.next || '/';
    const signedIn = document.body.dataset.signedIn === 'true';
    function getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
        return match ? decodeURIComponent(match[1]) : '';
    }
    const form = document.getElementById('auth-form');
    const tokenInput = document.getElementById('token-input');
    const errorBox = document.getElementById('auth-error');
    const submitButton = document.getElementById('auth-submit');
    const cancelLink = document.getElementById('auth-cancel');
    const signedInPanel = document.getElementById('signed-in-panel');
    const continueButton = document.getElementById('continue-button');
    const signoutButton = document.getElementById('signout-button');

    if (!form || !tokenInput || !errorBox || !submitButton || !cancelLink || !signedInPanel || !continueButton || !signoutButton) {
        return;
    }

    cancelLink.href = next;

    function setError(message) {
        if (!message) {
            errorBox.hidden = true;
            errorBox.textContent = '';
            return;
        }
        errorBox.hidden = false;
        errorBox.textContent = message;
    }

    async function signOut() {
        const csrfToken = getCsrfToken();
        const response = await fetch('/signout', {
            method: 'POST',
            headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
        });
        if (!response.ok) {
            setError('Sign-out failed. Please try again.');
            return;
        }
        let redirect = '/';
        try {
            const data = await response.json();
            if (data.redirect) redirect = data.redirect;
        } catch {
            // Non-JSON body — fall back to root
        }
        window.location.href = redirect;
    }

    if (signedIn) {
        form.hidden = true;
        signedInPanel.hidden = false;
        continueButton.addEventListener('click', () => {
            window.location.href = next;
        });
        signoutButton.addEventListener('click', async () => {
            signoutButton.disabled = true;
            try {
                await signOut();
            } finally {
                signoutButton.disabled = false;
            }
        });
        return;
    }

    tokenInput.focus();

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const token = tokenInput.value.trim();
        if (!token) {
            setError('Bitte einen gültigen Schlüssel eingeben.');
            tokenInput.focus();
            return;
        }

        setError('');
        submitButton.disabled = true;

        try {
            const resp = await fetch('/auth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, next }),
            });

            if (resp.ok) {
                const data = await resp.json();
                window.location.href = data.redirect;
                return;
            }

            setError('Ungültiger Schlüssel. Erneut versuchen.');
            tokenInput.select();
        } catch (_error) {
            setError('Anmeldung derzeit nicht möglich. Verbindung prüfen und erneut versuchen.');
        } finally {
            submitButton.disabled = false;
        }
    });
})();

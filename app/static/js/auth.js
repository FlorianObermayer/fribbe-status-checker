(async function auth() {
    const next = document.body.dataset.next || '/';
    const signedIn = document.body.dataset.signedIn === 'true';

    if (signedIn) {
        const wantsSignout = window.confirm('Du bist bereits angemeldet. Möchtest du dich abmelden?');
        if (!wantsSignout) {
            window.location.href = '/';
            return;
        }
        await fetch('/signout', { method: 'POST' });
        window.location.href = '/';
        return;
    }

    let message = 'API-Schlüssel eingeben:';
    while (true) {
        const token = window.prompt(message);
        if (token === null) {
            window.location.href = '/';
            return;
        }
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
        message = 'Ungültiger Schlüssel. Erneut versuchen:';
    }
})();

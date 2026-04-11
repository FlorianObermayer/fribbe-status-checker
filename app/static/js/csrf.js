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

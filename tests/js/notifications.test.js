/**
 * Tests for the notification dismissal logic (app/static/js/app.js).
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { hashString, computeNotificationState, NOTIFICATION_DISMISSED_KEY } from '../../app/static/js/app.js';

function storeHash(hash) {
    localStorage.setItem(NOTIFICATION_DISMISSED_KEY, hash);
}

function getStoredHash() {
    return localStorage.getItem(NOTIFICATION_DISMISSED_KEY);
}

// Mirrors what app.js does: call the pure function, then apply the clearHash side-effect.
function poll(html, textContent) {
    const result = computeNotificationState(html, textContent, getStoredHash());
    if (result.clearHash) localStorage.removeItem(NOTIFICATION_DISMISSED_KEY);
    return result;
}

beforeEach(() => {
    localStorage.clear();
});

describe('hashString', () => {
    it('returns consistent values for the same input', () => {
        expect(hashString('same content')).toBe(hashString('same content'));
    });

    it('returns different values for different input', () => {
        expect(hashString('notification A')).not.toBe(hashString('notification B'));
    });
});

describe('notification dismissal', () => {
    const NOTIF_HTML = '<div data-notification-id="nid-1"><p>Hello World</p></div>\n';
    const NOTIF_TEXT = 'Hello World\n';  // what textContent yields after setting innerHTML

    it('shows notification on first poll when no hash stored', () => {
        const { dismissed } = poll(NOTIF_HTML, NOTIF_TEXT);
        expect(dismissed).toBe(false);
    });

    it('stays hidden after user dismisses and same notification is polled again', () => {
        storeHash(hashString(NOTIF_TEXT));
        const { dismissed } = poll(NOTIF_HTML, NOTIF_TEXT);
        expect(dismissed).toBe(true);
    });

    it('shows again when notification content changes after dismissal', () => {
        storeHash(hashString('Notification A\n'));
        const { dismissed } = poll(
            '<div data-notification-id="nid-2"><p>Notification B</p></div>\n',
            'Notification B\n',
        );
        expect(dismissed).toBe(false);
    });
});

describe('dismissed hash survives empty response', () => {
    const NOTIF_TEXT = 'Hello World\n';

    it('does NOT clear the dismissed hash when server returns empty', () => {
        storeHash(hashString(NOTIF_TEXT));
        poll('', '');
        expect(getStoredHash()).not.toBeNull();
    });

    it('stays hidden when the same notification reappears after being temporarily disabled', () => {
        storeHash(hashString(NOTIF_TEXT));
        poll('', '');
        const { dismissed } = poll(
            '<div data-notification-id="nid-1"><p>Hello World</p></div>\n',
            NOTIF_TEXT,
        );
        expect(dismissed).toBe(true);
    });
});



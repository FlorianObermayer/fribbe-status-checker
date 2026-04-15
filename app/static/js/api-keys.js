(function () {
    'use strict';

    var body = document.body;
    var apiKeysUrl = body.getAttribute('data-url-api-keys');
    var apiKeyUrl = body.getAttribute('data-url-api-key');
    var ROLE_LABELS = JSON.parse(body.getAttribute('data-role-labels') || '{}');
    var adminRoleLabel = body.getAttribute('data-role-label-admin');

    var form = document.getElementById('create-key-form');
    var createBtn = document.getElementById('create-key-btn');
    var commentInput = document.getElementById('key-comment');
    var roleSelect = document.getElementById('key-role');
    var validUntilInput = document.getElementById('key-valid-until');

    var newKeyBanner = document.getElementById('new-key-banner');
    var newKeyValue = document.getElementById('new-key-value');
    var copyKeyBtn = document.getElementById('copy-key-btn');

    var keyListLoading = document.getElementById('key-list-loading');
    var keyListEmpty = document.getElementById('key-list-empty');
    var keyListTable = document.getElementById('key-list-table');
    var keyListBody = document.getElementById('key-list-body');

    var deleteOverlay = document.getElementById('delete-confirm-overlay');
    var deletePrefix = document.getElementById('delete-confirm-prefix');
    var deleteYes = document.getElementById('delete-confirm-yes');
    var deleteNo = document.getElementById('delete-confirm-no');

    var pendingDeletePrefix = '';
    var selfKeyPrefix = null;
    var currentKeys = [];
    var currentAdminPrefix = null;
    var sortColumn = null;
    var sortDir = 'asc';

    function formatDate(isoStr) {
        try {
            var d = new Date(isoStr);
            return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
        } catch (_e) {
            return isoStr;
        }
    }

    function isExpired(isoStr) {
        try {
            return new Date(isoStr) < new Date();
        } catch (_e) {
            return false;
        }
    }

    function loadKeys() {
        keyListLoading.classList.remove('hidden');
        keyListEmpty.classList.add('hidden');
        keyListTable.classList.add('hidden');

        fetch(apiKeysUrl, {
            headers: withCsrfHeaders({ 'Accept': 'application/json' }),
            credentials: 'same-origin'
        })
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                keyListLoading.classList.add('hidden');
                selfKeyPrefix = data.self_key_prefix || null;
                currentKeys = data.api_keys || [];
                currentAdminPrefix = data.admin_token_prefix || null;
                renderKeys(sortedKeys(), currentAdminPrefix);
            })
            .catch(function () {
                keyListLoading.textContent = 'Fehler beim Laden der Schlüssel.';
            });
    }

    function sortedKeys() {
        if (!sortColumn) return currentKeys.slice();
        return currentKeys.slice().sort(function (a, b) {
            var av, bv;
            if (sortColumn === 'role') {
                av = a.role || 0;
                bv = b.role || 0;
            } else {
                av = a.valid_until ? new Date(a.valid_until).getTime() : Infinity;
                bv = b.valid_until ? new Date(b.valid_until).getTime() : Infinity;
            }
            if (av < bv) return sortDir === 'asc' ? -1 : 1;
            if (av > bv) return sortDir === 'asc' ? 1 : -1;
            return 0;
        });
    }

    function updateSortHeaders() {
        var headers = keyListTable.querySelectorAll('th[data-sort]');
        headers.forEach(function (th) {
            if (th.getAttribute('data-sort') === sortColumn) {
                th.setAttribute('aria-sort', sortDir === 'asc' ? 'ascending' : 'descending');
            } else {
                th.setAttribute('aria-sort', 'none');
            }
        });
    }

    function setupSortHeaders() {
        var headers = keyListTable.querySelectorAll('th[data-sort]');
        headers.forEach(function (th) {
            th.addEventListener('click', function () {
                var col = th.getAttribute('data-sort');
                if (sortColumn === col) {
                    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    sortColumn = col;
                    sortDir = 'asc';
                }
                updateSortHeaders();
                renderKeys(sortedKeys(), currentAdminPrefix);
            });
        });
    }

    function renderAdminTokenRow(prefix) {
        var tr = document.createElement('tr');
        tr.className = 'admin-token-row';

        var tdPrefix = document.createElement('td');
        tdPrefix.className = 'key-prefix';
        tdPrefix.textContent = prefix;
        tr.appendChild(tdPrefix);

        var tdComment = document.createElement('td');
        tdComment.textContent = 'Admin-Token';
        tr.appendChild(tdComment);

        var tdRole = document.createElement('td');
        var badge = document.createElement('span');
        badge.className = 'role-badge';
        badge.textContent = adminRoleLabel;
        tdRole.appendChild(badge);
        tr.appendChild(tdRole);

        var tdValid = document.createElement('td');
        tdValid.textContent = '—';
        tr.appendChild(tdValid);

        var tdActions = document.createElement('td');
        var hint = document.createElement('span');
        hint.className = 'self-hint';
        hint.textContent = '(env)';
        tdActions.appendChild(hint);
        tr.appendChild(tdActions);

        keyListBody.appendChild(tr);
    }

    function renderKeys(keys, adminTokenPrefix) {
        keyListBody.innerHTML = '';
        if (adminTokenPrefix) {
            renderAdminTokenRow(adminTokenPrefix);
        }
        if (keys.length === 0 && !adminTokenPrefix) {
            keyListEmpty.classList.remove('hidden');
            keyListTable.classList.add('hidden');
            return;
        }
        keyListEmpty.classList.add('hidden');
        keyListTable.classList.remove('hidden');

        keys.forEach(function (k) {
            var tr = document.createElement('tr');
            var expired = isExpired(k.valid_until);

            var tdPrefix = document.createElement('td');
            tdPrefix.className = 'key-prefix';
            tdPrefix.textContent = k.key_prefix;
            tr.appendChild(tdPrefix);

            var tdComment = document.createElement('td');
            tdComment.textContent = k.comment || '—';
            tr.appendChild(tdComment);

            var tdRole = document.createElement('td');
            var badge = document.createElement('span');
            badge.className = 'role-badge';
            badge.textContent = ROLE_LABELS[k.role] || k.role;
            tdRole.appendChild(badge);
            tr.appendChild(tdRole);

            var tdValid = document.createElement('td');
            tdValid.textContent = formatDate(k.valid_until);
            if (expired) tdValid.className = 'expired';
            tr.appendChild(tdValid);

            var tdActions = document.createElement('td');
            var isSelf = selfKeyPrefix && k.key_prefix === selfKeyPrefix;
            if (isSelf) {
                var selfHint = document.createElement('span');
                selfHint.className = 'self-hint';
                selfHint.textContent = '(eigener)';
                tdActions.appendChild(selfHint);
            } else {
                var deleteBtn = document.createElement('button');
                deleteBtn.className = 'delete-btn';
                deleteBtn.title = 'Löschen';
                deleteBtn.setAttribute('aria-label', 'Schlüssel löschen');
                deleteBtn.innerHTML =
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
                    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
                    '<polyline points="3 6 5 6 21 6"/>' +
                    '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>' +
                    '<path d="M10 11v6"/><path d="M14 11v6"/>' +
                    '<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>' +
                    '</svg>';
                deleteBtn.addEventListener('click', function () {
                    showDeleteConfirm(k.key_prefix);
                });
                tdActions.appendChild(deleteBtn);
            }
            tr.appendChild(tdActions);

            keyListBody.appendChild(tr);
        });
    }

    function showDeleteConfirm(prefix) {
        pendingDeletePrefix = prefix;
        deletePrefix.textContent = prefix;
        deleteOverlay.classList.remove('hidden');
    }

    function hideDeleteConfirm() {
        deleteOverlay.classList.add('hidden');
        pendingDeletePrefix = '';
    }

    function deleteKey(prefix) {
        // Strip trailing ellipsis to get the raw prefix for the API
        var rawPrefix = prefix.replace(/\.{3}$/, '');
        fetch(apiKeyUrl, {
            method: 'DELETE',
            headers: withCsrfHeaders({ 'Content-Type': 'application/json', 'Accept': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({ key: rawPrefix })
        })
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                hideDeleteConfirm();
                loadKeys();
            })
            .catch(function () {
                hideDeleteConfirm();
                alert('Fehler beim Löschen des Schlüssels.');
            });
    }

    function createKey(evt) {
        evt.preventDefault();
        var comment = commentInput.value.trim();
        var minLen = parseInt(commentInput.getAttribute('minlength') || '1', 10);
        var maxLen = parseInt(commentInput.getAttribute('maxlength') || '9999', 10);
        if (comment.length < minLen || comment.length > maxLen) {
            commentInput.focus();
            return;
        }
        createBtn.disabled = true;

        var payload = { comment: comment, role: parseInt(roleSelect.value, 10) };

        if (validUntilInput.value) {
            payload.valid_until = new Date(validUntilInput.value).toISOString();
        }

        fetch(apiKeyUrl, {
            method: 'POST',
            headers: withCsrfHeaders({ 'Content-Type': 'application/json', 'Accept': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        })
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                createBtn.disabled = false;
                commentInput.value = '';
                validUntilInput.value = '';

                // Show the new key value
                newKeyValue.textContent = data.key;
                newKeyBanner.classList.remove('hidden');

                loadKeys();
            })
            .catch(function () {
                createBtn.disabled = false;
                showToast('Fehler beim Erstellen des Schlüssels.', 'error');
            });
    }

    function copyKey() {
        var key = newKeyValue.textContent;
        copyTextToClipboard(key)
            .then(function () { showToast('Schlüssel kopiert'); })
            .catch(function () { showToast('Fehler beim Kopieren', 'error'); });
    }

    // Event listeners
    form.addEventListener('submit', createKey);
    copyKeyBtn.addEventListener('click', copyKey);
    deleteYes.addEventListener('click', function () { deleteKey(pendingDeletePrefix); });
    deleteNo.addEventListener('click', hideDeleteConfirm);
    deleteOverlay.addEventListener('click', function (e) {
        if (e.target === deleteOverlay) hideDeleteConfirm();
    });

    // Setup sort headers and initial load
    setupSortHeaders();
    loadKeys();
})();


// Load Markdown Editor
const easyMDE = new EasyMDE({
    element: document.getElementById('message'),
    autosave: {
        enabled: true,
        timeFormat: "locale: de-DE, format: HH:mm",
        uniqueId: "unique-id",
    },
    autoDownloadFontAwesome: false,
    previewImagesInEditor: true,
    spellChecker: false,
    toolbar: false,
    forceSync: true,
});

const submitBtn = document.getElementById('submitBtn');
function updateSubmitState() {
    submitBtn.disabled = easyMDE.value().trim() === '';
}
updateSubmitState();
easyMDE.codemirror.on('change', updateSubmitState);


import * as State from './state.js';

export function togglePreview(idx) {
    const audio = document.getElementById(`audio-${idx}`);
    const btn = document.getElementById(`preview-${idx}`);
    if (!audio || !btn) return;

    if (State._currentPreviewIdx !== null && State._currentPreviewIdx !== idx) {
        const prev = document.getElementById(`audio-${State._currentPreviewIdx}`);
        const prevBtn = document.getElementById(`preview-${State._currentPreviewIdx}`);
        if (prev) { prev.pause(); prev.currentTime = 0; }
        if (prevBtn) prevBtn.textContent = '▶';
        State.setCurrentPreviewIdx(null);
    }

    if (audio.paused) {
        audio.play().catch(() => {});
        btn.textContent = '⏹';
        State.setCurrentPreviewIdx(idx);
        audio.onended = () => { btn.textContent = '▶'; State.setCurrentPreviewIdx(null); };
    } else {
        audio.pause();
        audio.currentTime = 0;
        btn.textContent = '▶';
        State.setCurrentPreviewIdx(null);
    }
}

export function openPreviewOverlay(url, title) {
    const overlay = document.getElementById('spotifyPreviewOverlay');
    if (!overlay) return;
    const iframe = overlay.querySelector('iframe');
    if (iframe) iframe.src = url;
    const titleEl = overlay.querySelector('.preview-title');
    if (titleEl && title) titleEl.textContent = title;
    overlay.classList.add('open');
}

export function closePreviewOverlay() {
    const overlay = document.getElementById('spotifyPreviewOverlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    const iframe = overlay.querySelector('iframe');
    if (iframe) iframe.src = '';
}

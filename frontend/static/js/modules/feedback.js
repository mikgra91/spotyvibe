import * as State from './state.js';
import { showToast } from './ui.js';

export function toggleFeedback(idx, action) {
    if (State.openFormIndex !== null && State.openFormIndex !== idx) {
        closeFeedback(State.openFormIndex);
    }

    const form = document.getElementById(`form-${idx}`);
    const isOpen = form.classList.contains('open');

    if (isOpen && State.openFormAction === action) {
        closeFeedback(idx);
        return;
    }

    form.classList.add('open');
    State.setOpenFormIndex(idx);
    State.setOpenFormAction(action);

    const submitBtn = document.getElementById(`submitBtn-${idx}`);
    if (action === 'like') {
        submitBtn.textContent = '👍 Submit Like';
        submitBtn.className = 'btn btn-submit-like';
    } else {
        submitBtn.textContent = '👎 Submit Dislike';
        submitBtn.className = 'btn btn-submit-dislike';
    }
}

export function closeFeedback(idx) {
    const form = document.getElementById(`form-${idx}`);
    if (form) form.classList.remove('open');
    if (State.openFormIndex === idx) {
        State.setOpenFormIndex(null);
        State.setOpenFormAction(null);
    }
}

export async function submitFeedback(idx) {
    const artist = document.getElementById(`artist-${idx}`).value.trim();
    const track  = document.getElementById(`title-${idx}`).value.trim();
    const reason = document.getElementById(`reason-${idx}`).value.trim();

    if (!artist) { alert('Artist is required.'); return; }

    const submitBtn = document.getElementById(`submitBtn-${idx}`);
    submitBtn.disabled = true;
    submitBtn.textContent = '…';

    try {
        const resp = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: State.openFormAction,
                artist,
                track:  track  || null,
                reason: reason || null,
            }),
        });

        if (!resp.ok) {
            const data = await resp.json();
            alert('Error: ' + (data.error || 'unknown'));
            return;
        }

        const data = await resp.json();
        const trackLabel = track ? ` — ${track}` : '';

        if (State.openFormAction === 'dislike') {
            const removed = data.removal && data.removal.removed;
            const msg = removed
                ? `👎 Disliked & removed from playlist: ${artist}${trackLabel}`
                : `👎 Disliked: ${artist}${trackLabel}`;
            showToast(msg);
        } else {
            showToast(`👍 Liked: ${artist}${trackLabel}`);
        }

        const fbTrack = State.suggestions[idx];
        animateRemove(idx);

        if (fbTrack) {
            fetch('/api/songlist/track', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist: fbTrack.artist, track: fbTrack.track }),
            }).catch(() => {});
        }
    } catch (e) {
        alert('Network error: ' + e.message);
    } finally {
        submitBtn.disabled = false;
    }
}

export async function removeTrack(idx) {
    const track = State.suggestions[idx];
    if (!track) { animateRemove(idx); return; }

    try {
        const resp = await fetch('/api/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist: track.artist, track: track.track }),
        });
        const data = await resp.json();
        const msg = data.removed
            ? `Removed from playlist: ${track.artist} — ${track.track}`
            : `Removed: ${track.artist} — ${track.track}`;
        showToast(msg);
    } catch (e) {
        /* Network error — still remove from UI */
    }

    animateRemove(idx);

    if (track) {
        fetch('/api/songlist/track', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist: track.artist, track: track.track }),
        }).catch(() => {});
    }
}

export function animateRemove(idx) {
    const el = document.getElementById(`track-${idx}`);
    if (!el) return;
    el.style.opacity = '0';
    el.style.transform = 'translateX(40px)';
    setTimeout(() => el.remove(), 300);

    State.spliceSuggestion(idx);

    if (State.openFormIndex === idx) {
        State.setOpenFormIndex(null);
        State.setOpenFormAction(null);
    }
}

/**
 * voice.js — Web Speech API voice input for profile description (Wave 4 C.2)
 */
import { i18n } from './i18n.js';
import { showToast } from './ui.js';
import { el } from './dom.js';

const SUPPORT = (typeof window !== 'undefined')
    && (window.SpeechRecognition || window.webkitSpeechRecognition);


const LANG_MAP = { en: 'en-US', de: 'de-DE', jp: 'ja-JP' };

let _current = null;
let _lastProcessedIdx = 0;

function _dismissListeningToast() {
    const toast = el('toast');
    if (toast) toast.classList.remove('show');
}

function _getUiLang() {
    try { return localStorage.getItem('svLang') || 'en'; } catch { return 'en'; }
}

export function toggleVoice(targetInputId) {
    if (!SUPPORT) return;
    if (_current) { _current.stop(); _current = null; return; }

    const Recog = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new Recog();
    rec.lang = LANG_MAP[_getUiLang()] || 'en-US';
    rec.continuous = true;
    rec.interimResults = false;

    const target = el(targetInputId);
    const button = el('voiceBtnVibe');
    const srStatus = el('voiceSrStatus');

    rec.onstart = () => {
        _lastProcessedIdx = 0;
        if (button) {
            button.classList.add('voice-btn--recording');
            button.setAttribute('aria-pressed', 'true');
        }
        if (srStatus) srStatus.textContent = i18n('voice.started', 'Recording started');
        showToast(i18n('voice.listening', 'We are listening …'), 'info', 600000);
    };

    rec.onresult = (e) => _appendTranscriptAtCursor(target, e.results);

    rec.onerror = (e) => {
        _dismissListeningToast();
        if (e.error === 'not-allowed' || e.error === 'permission-denied') {
            showToast(i18n('voice.permission_denied', 'Mic access denied. Grant permission in your browser, then try again.'));
        } else if (e.error === 'network') {
            showToast(i18n('voice.network', 'Voice input needs a connection.'));
        }
        // no-speech: silently ignore
    };

    rec.onend = () => {
        if (button) {
            button.classList.remove('voice-btn--recording');
            button.setAttribute('aria-pressed', 'false');
        }
        if (srStatus) srStatus.textContent = i18n('voice.stopped', 'Recording stopped — transcript added');
        _dismissListeningToast();
        _current = null;
    };

    rec.start();
    _current = rec;
}

function _appendTranscriptAtCursor(textarea, results) {
    if (!textarea) return;
    // Only process new results since the last call to avoid duplicates
    // when continuous=true (onresult fires with ALL results each time).
    const transcript = Array.from(results)
        .slice(_lastProcessedIdx)
        .filter(r => r.isFinal)
        .map(r => r[0].transcript)
        .join(' ');
    // Advance the index past all results we've seen (final or interim)
    _lastProcessedIdx = results.length;
    if (!transcript) return;

    const start = textarea.selectionStart || textarea.value.length;
    const end = textarea.selectionEnd || start;
    const before = textarea.value.slice(0, start);
    const after = textarea.value.slice(end);
    const needsSpaceBefore = before && !/\s$/.test(before);
    const prefix = needsSpaceBefore ? ' ' : '';
    textarea.value = before + prefix + transcript + after;
    const newPos = (before + prefix + transcript).length;
    textarea.selectionStart = textarea.selectionEnd = newPos;
    textarea.dispatchEvent(new Event('input'));
}

export function init() {
    window.toggleVoice = toggleVoice;

    const btn = el('voiceBtnVibe');
    if (!btn) return;

    // Hide on unsupported browsers
    if (!SUPPORT) {
        btn.classList.add('hidden');
        return;
    }

    // Browser supports Speech API — show the button
    btn.classList.remove('hidden');
}


/**
 * voice.js — Web Speech API voice input for profile description (Wave 4 C.2)
 */
import { i18n } from './i18n.js';
import { showToast } from './ui.js';

const SUPPORT = (typeof window !== 'undefined')
    && (window.SpeechRecognition || window.webkitSpeechRecognition);

export function isSupported() { return !!SUPPORT; }

const LANG_MAP = { en: 'en-US', de: 'de-DE' };

let _current = null;

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

    const target = document.getElementById(targetInputId);
    const button = document.getElementById('voiceBtnVibe');
    const srStatus = document.getElementById('voiceSrStatus');

    rec.onstart = () => {
        if (button) {
            button.classList.add('voice-btn--recording');
            button.setAttribute('aria-pressed', 'true');
        }
        if (srStatus) srStatus.textContent = i18n('voice.started', 'Recording started');
    };

    rec.onresult = (e) => _appendTranscriptAtCursor(target, e.results);

    rec.onerror = (e) => {
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
        _current = null;
    };

    rec.start();
    _current = rec;
}

function _appendTranscriptAtCursor(textarea, results) {
    if (!textarea) return;
    const transcript = Array.from(results)
        .filter(r => r.isFinal)
        .map(r => r[0].transcript)
        .join(' ');
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

    const btn = document.getElementById('voiceBtnVibe');
    if (!btn) return;

    // Hide on unsupported browsers
    if (!SUPPORT) {
        btn.classList.add('hidden');
        return;
    }

    // Hide on WebView (Android)
    if (/; wv\)/.test(navigator.userAgent)) {
        btn.classList.add('hidden');
        return;
    }
}


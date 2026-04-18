/**
 * Spotify Web Playback SDK loader and lifecycle wrapper.
 *
 * Keeps preview.js readable by isolating the SDK's script-load,
 * player-connect, and event plumbing. The public surface is a small
 * set of promise-returning functions plus an event bus.
 *
 * The SDK itself is an IE-era global (`window.Spotify.Player`) that
 * registers itself after `window.onSpotifyWebPlaybackSDKReady` fires.
 * We adapt that into a modern promise.
 */

const SDK_SRC = 'https://sdk.scdn.co/spotify-player.js';
const TOKEN_ENDPOINT = '/api/spotify/token';

let _loadPromise = null;
let _player = null;
let _deviceId = null;
const _listeners = new Map();

/**
 * Load the SDK script and resolve once `window.Spotify.Player` exists.
 * Idempotent.
 */
export function loadSdk() {
    if (_loadPromise) return _loadPromise;
    _loadPromise = new Promise((resolve, reject) => {
        if (window.Spotify && window.Spotify.Player) {
            resolve(window.Spotify);
            return;
        }
        const existing = document.querySelector(`script[src="${SDK_SRC}"]`);
        window.onSpotifyWebPlaybackSDKReady = () => resolve(window.Spotify);
        if (existing) return;
        const s = document.createElement('script');
        s.src = SDK_SRC;
        s.async = true;
        s.onerror = () => reject(new Error('sdk_script_failed'));
        document.head.appendChild(s);
    });
    return _loadPromise;
}

async function fetchToken() {
    const res = await fetch(TOKEN_ENDPOINT, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('token_fetch_failed');
    const data = await res.json();
    if (!data.access_token) throw new Error('no_token');
    return data.access_token;
}

function emit(event, payload) {
    const set = _listeners.get(event);
    if (!set) return;
    set.forEach((cb) => {
        try { cb(payload); } catch (e) { console.error('[spotify-sdk] listener error', e); }
    });
}

export function on(event, cb) {
    if (!_listeners.has(event)) _listeners.set(event, new Set());
    _listeners.get(event).add(cb);
    return () => _listeners.get(event)?.delete(cb);
}

/**
 * Initialise and connect the Spotify Player. Resolves with
 * ``{player, deviceId}`` on success.
 *
 * Events emitted: ``ready``, ``not_ready``, ``state_changed``,
 * ``initialization_error``, ``authentication_error``, ``account_error``,
 * ``playback_error``.
 */
export async function connect({ name = 'SpotyVibe Player', volume = 0.8 } = {}) {
    if (_player) return { player: _player, deviceId: _deviceId };

    const Spotify = await loadSdk();

    const player = new Spotify.Player({
        name,
        volume,
        getOAuthToken: (cb) => {
            fetchToken().then(cb).catch((err) => {
                emit('authentication_error', { message: String(err) });
            });
        },
    });

    player.addListener('ready', ({ device_id }) => {
        _deviceId = device_id;
        emit('ready', { deviceId: device_id });
    });
    player.addListener('not_ready', ({ device_id }) => {
        emit('not_ready', { deviceId: device_id });
    });
    player.addListener('player_state_changed', (state) => {
        emit('state_changed', state);
    });
    ['initialization_error', 'authentication_error', 'account_error', 'playback_error'].forEach((evt) => {
        player.addListener(evt, (e) => emit(evt, e));
    });

    const connected = await player.connect();
    if (!connected) throw new Error('player_connect_failed');

    _player = player;
    return { player, deviceId: _deviceId };
}

/**
 * Start playback of a single track URI on our device.
 * Caller is responsible for having awaited ``connect()`` and the
 * ``ready`` event so ``deviceId`` exists.
 */
export async function playTrack(trackId) {
    if (!_deviceId) throw new Error('no_device');
    const token = await fetchToken();
    const res = await fetch(`https://api.spotify.com/v1/me/player/play?device_id=${encodeURIComponent(_deviceId)}`, {
        method: 'PUT',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ uris: [`spotify:track:${trackId}`] }),
    });
    if (!res.ok && res.status !== 204) {
        throw new Error(`play_failed_${res.status}`);
    }
}

export function togglePlay() {
    return _player ? _player.togglePlay() : Promise.reject(new Error('no_player'));
}

export function seek(positionMs) {
    return _player ? _player.seek(positionMs) : Promise.reject(new Error('no_player'));
}

export function getPlayer() { return _player; }
export function getDeviceId() { return _deviceId; }

/**
 * Disconnect and dispose of the player (e.g. when closing the overlay
 * or falling back to the iframe). Safe to call multiple times.
 */
export function disconnect() {
    if (_player) {
        try { _player.disconnect(); } catch (_) { /* ignore */ }
        _player = null;
        _deviceId = null;
    }
    _listeners.clear();
}

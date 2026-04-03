/**
 * Scroll-aware section jump bubble.
 *
 * Shows a neon-glass bubble in the bottom-left corner:
 * - When the Spotify section header is below the viewport → arrow down (jump to Spotify)
 * - When the Spotify section header is visible or above → arrow up (jump to OpenAI)
 */

const ARROW_DOWN = '▼';
const ARROW_UP = '▲';

let bubble = null;
let openaiSection = null;
let spotifySection = null;
let spotifyHeader = null;

/**
 * Determine direction based on whether the Spotify header is still
 * below the viewport.  If its top edge is in the bottom half of the
 * viewport or below, the user hasn't reached Spotify yet → show "jump down".
 */
function shouldJumpDown() {
    if (!spotifyHeader) return true;
    const rect = spotifyHeader.getBoundingClientRect();
    // Header's top is in the lower half or below the viewport → user is still in the OpenAI area
    return rect.top > window.innerHeight * 0.5;
}

function update() {
    if (!bubble || !openaiSection || !spotifySection) return;

    const down = shouldJumpDown();

    bubble.textContent = down ? ARROW_DOWN : ARROW_UP;
    bubble.title = down ? 'Jump to Spotify' : 'Jump to OpenAI';
    bubble.classList.remove('hidden');
}

function onClick() {
    if (shouldJumpDown()) {
        const header = spotifySection.querySelector('.provider-header') || spotifySection;
        header.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
        const header = openaiSection.querySelector('.provider-header') || openaiSection;
        header.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

export function initJumpBubble() {
    bubble = document.getElementById('sectionJumpBubble');
    openaiSection = document.querySelector('.provider-openai');
    spotifySection = document.querySelector('.provider-spotify');
    spotifyHeader = spotifySection ? spotifySection.querySelector('.provider-header') : null;

    if (!bubble || !openaiSection || !spotifySection) return;

    bubble.addEventListener('click', onClick);

    // Throttled scroll handler
    let ticking = false;
    window.addEventListener('scroll', () => {
        if (!ticking) {
            ticking = true;
            requestAnimationFrame(() => {
                update();
                ticking = false;
            });
        }
    }, { passive: true });

    // Initial state
    update();
}

export function refreshJumpBubble() {
    openaiSection = document.querySelector('.provider-openai');
    spotifySection = document.querySelector('.provider-spotify');
    spotifyHeader = spotifySection ? spotifySection.querySelector('.provider-header') : null;
    update();
}

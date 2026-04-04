export const THEME_BACKGROUNDS = {
    equalizer: `<canvas id="equalizerCanvas"></canvas>`,
    pulse: `<canvas id="pulseCanvas"></canvas>`,
    spectrum: `<canvas id="spectrumCanvas"></canvas>`,
    starfield: `<canvas id="starfieldCanvas"></canvas>`,
};

export const THEME_RENDERERS = {};

export function switchTheme(theme) {
    if (THEME_RENDERERS._stopCurrent) THEME_RENDERERS._stopCurrent();

    document.body.className = 'theme-' + theme;

    const bg = document.getElementById('themeBackground');
    bg.innerHTML = THEME_BACKGROUNDS[theme] || '';

    const canvas = bg.querySelector('canvas');
    if (canvas && THEME_RENDERERS[theme]) {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        THEME_RENDERERS._stopCurrent = THEME_RENDERERS[theme](canvas);

        const resizeHandler = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        };
        window.addEventListener('resize', resizeHandler);
        const prevStop = THEME_RENDERERS._stopCurrent;
        THEME_RENDERERS._stopCurrent = () => {
            if (prevStop) prevStop();
            window.removeEventListener('resize', resizeHandler);
        };
    }

    document.querySelectorAll('.style-switcher-btn').forEach(btn => {
        const isActive = btn.dataset.theme === theme;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-checked', isActive.toString());
    });

    try { localStorage.setItem('spotyvibe-theme', theme); } catch(e) {}
}

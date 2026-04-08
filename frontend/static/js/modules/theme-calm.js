import { THEME_RENDERERS } from './theme-switcher.js';

THEME_RENDERERS.calm = (canvas) => {
    const ctx = canvas.getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
    grad.addColorStop(0, '#0d1117');
    grad.addColorStop(1, '#0a0e17');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    return () => {};
};

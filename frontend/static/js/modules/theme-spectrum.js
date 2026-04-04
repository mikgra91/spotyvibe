import { THEME_RENDERERS } from './theme-switcher.js';

THEME_RENDERERS.spectrum = function(canvas) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        return () => {};
    }

    const ctx = canvas.getContext('2d');
    let animId;
    let stopped = false;

    const isMobile = window.innerWidth <= 768;
    const BAR_COUNT = isMobile ? 40 : 60;
    const INNER_RADIUS_FRAC = 0.27;
    const MAX_LENGTH_FRAC = 0.79;

    const palette = [
        [30, 215, 96],
        [25, 211, 170],
        [0, 200, 220],
        [40, 160, 255],
        [76, 120, 255],
        [120, 80, 255],
        [170, 60, 255],
        [210, 50, 230],
        [255, 70, 180]
    ];

    function lerpColor(a, b, t) {
        return [
            a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t
        ];
    }

    function getColor(t) {
        var f = t * (palette.length - 1);
        var lo = Math.floor(f);
        var hi = Math.min(lo + 1, palette.length - 1);
        return lerpColor(palette[lo], palette[hi], f - lo);
    }

    var phases = new Float32Array(BAR_COUNT);
    for (var i = 0; i < BAR_COUNT; i++) {
        phases[i] = Math.random() * Math.PI * 2;
    }

    var t = 0;

    function draw() {
        if (stopped) return;

        if (document.visibilityState === 'hidden') {
            animId = requestAnimationFrame(draw);
            return;
        }

        var w = canvas.width, h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        var cx = w / 2;
        var cy = h / 2 + 200;
        var minDim = Math.min(w, h);
        var innerR = minDim * INNER_RADIUS_FRAC;
        var maxLen = minDim * MAX_LENGTH_FRAC;

        for (var i = 0; i < BAR_COUNT; i++) {
            var angle = (i / BAR_COUNT) * Math.PI * 2;
            var wave1 = Math.sin(t + i * 0.15 + phases[i]) * 0.5 + 0.5;
            var wave2 = Math.sin(t * 0.7 + i * 0.3 + phases[i] * 1.5) * 0.3 + 0.5;
            var length = maxLen * (0.3 + 0.7 * wave1 * wave2);

            var cosA = Math.cos(angle);
            var sinA = Math.sin(angle);
            var x1 = cx + cosA * innerR;
            var y1 = cy + sinA * innerR;
            var x2 = cx + cosA * (innerR + length);
            var y2 = cy + sinA * (innerR + length);

            var col = getColor(i / (BAR_COUNT - 1));
            var cr = col[0] | 0, cg = col[1] | 0, cb = col[2] | 0;

            if (!isMobile) {
                ctx.shadowColor = 'rgba(' + cr + ',' + cg + ',' + cb + ',0.4)';
                ctx.shadowBlur = 6 + wave1 * 8;
            }

            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.strokeStyle = 'rgba(' + cr + ',' + cg + ',' + cb + ',' + (0.6 + wave1 * 0.35) + ')';
            ctx.lineWidth = isMobile ? 3 : 4.5;
            ctx.lineCap = 'round';
            ctx.stroke();
        }

        ctx.shadowBlur = 0;

        t += 0.03;

        if (isMobile) {
            setTimeout(function() { animId = requestAnimationFrame(draw); }, 17);
        } else {
            animId = requestAnimationFrame(draw);
        }
    }

    animId = requestAnimationFrame(draw);
    return function() { stopped = true; cancelAnimationFrame(animId); };
};

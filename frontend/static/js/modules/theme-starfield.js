import { THEME_RENDERERS } from './theme-switcher.js';

THEME_RENDERERS.starfield = function(canvas) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        return () => {};
    }

    const ctx = canvas.getContext('2d');
    let animId;
    let stopped = false;

    const isMobile = window.innerWidth <= 768;
    const STAR_COUNT = isMobile ? 120 : 300;
    const NEBULA_COUNT = isMobile ? 3 : 5;

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

    var stars = [];
    var nebulae = [];

    function initStars() {
        stars.length = 0;
        var w = canvas.width, h = canvas.height;
        for (var i = 0; i < STAR_COUNT; i++) {
            var depth = Math.random();
            stars.push({
                x: Math.random() * w,
                y: Math.random() * h,
                z: depth,
                size: 0.5 + depth * 2.5,
                speed: 0.05 + depth * 0.15,
                twinklePhase: Math.random() * Math.PI * 2,
                twinkleSpeed: 0.005 + Math.random() * 0.015,
                color: palette[Math.floor(Math.random() * palette.length)]
            });
        }
    }

    function initNebulae() {
        nebulae.length = 0;
        var w = canvas.width, h = canvas.height;
        for (var i = 0; i < NEBULA_COUNT; i++) {
            nebulae.push({
                x: Math.random() * w,
                y: Math.random() * h,
                radius: 100 + Math.random() * 250,
                color: palette[Math.floor(Math.random() * palette.length)],
                alpha: 0.03 + Math.random() * 0.04,
                driftX: (Math.random() - 0.5) * 0.08,
                driftY: (Math.random() - 0.5) * 0.06,
                phase: Math.random() * Math.PI * 2
            });
        }
    }

    initStars();
    initNebulae();

    function draw(time) {
        if (stopped) return;

        if (document.visibilityState === 'hidden') {
            animId = requestAnimationFrame(draw);
            return;
        }

        var w = canvas.width, h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        // Draw nebula blobs
        for (var n = 0; n < nebulae.length; n++) {
            var nb = nebulae[n];
            nb.x += nb.driftX;
            nb.y += nb.driftY;
            var pulse = 1 + Math.sin(time * 0.0003 + nb.phase) * 0.15;

            // Wrap around
            if (nb.x < -nb.radius) nb.x = w + nb.radius;
            if (nb.x > w + nb.radius) nb.x = -nb.radius;
            if (nb.y < -nb.radius) nb.y = h + nb.radius;
            if (nb.y > h + nb.radius) nb.y = -nb.radius;

            var grad = ctx.createRadialGradient(nb.x, nb.y, 0, nb.x, nb.y, nb.radius * pulse);
            var c = nb.color;
            grad.addColorStop(0, 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + (nb.alpha * 1.5) + ')');
            grad.addColorStop(0.4, 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + nb.alpha + ')');
            grad.addColorStop(1, 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',0)');
            ctx.fillStyle = grad;
            ctx.fillRect(nb.x - nb.radius * pulse, nb.y - nb.radius * pulse, nb.radius * 2 * pulse, nb.radius * 2 * pulse);
        }

        // Draw stars with parallax and twinkle
        for (var i = 0; i < stars.length; i++) {
            var s = stars[i];
            s.y -= s.speed;
            s.twinklePhase += s.twinkleSpeed;

            if (s.y < -s.size) {
                s.y = h + s.size;
                s.x = Math.random() * w;
            }

            var twinkle = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(s.twinklePhase));
            var c = s.color;
            var cr = c[0] | 0, cg = c[1] | 0, cb = c[2] | 0;

            if (!isMobile && s.z > 0.6) {
                ctx.shadowColor = 'rgba(' + cr + ',' + cg + ',' + cb + ',0.5)';
                ctx.shadowBlur = 4 + s.z * 6;
            }

            ctx.beginPath();
            ctx.arc(s.x, s.y, s.size * twinkle, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(' + cr + ',' + cg + ',' + cb + ',' + (twinkle * 0.9) + ')';
            ctx.fill();
        }

        ctx.shadowBlur = 0;

        if (isMobile) {
            setTimeout(function() { animId = requestAnimationFrame(draw); }, 17);
        } else {
            animId = requestAnimationFrame(draw);
        }
    }

    animId = requestAnimationFrame(draw);
    return function() { stopped = true; cancelAnimationFrame(animId); };
};

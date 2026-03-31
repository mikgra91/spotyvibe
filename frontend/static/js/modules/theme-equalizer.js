import { THEME_RENDERERS } from './theme-switcher.js';

THEME_RENDERERS.equalizer = function(canvas) {
    const ctx = canvas.getContext('2d');
    let animId;

    const BAR_COUNT  = 56;
    const GAP        = 3;
    const FLOOR_Y    = 0.98;
    const MAX_H_FRAC = 0.85;
    const SPRING     = 0.08;
    const DAMPING    = 0.78;
    const REFL_FRAC  = 0;

    const heights    = new Float32Array(BAR_COUNT);
    const targets    = new Float32Array(BAR_COUNT);
    const velocities = new Float32Array(BAR_COUNT);
    const phases     = new Float32Array(BAR_COUNT);

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

    function barColor(idx) {
        var f = idx / (BAR_COUNT - 1) * (palette.length - 1);
        var lo = Math.floor(f);
        var hi = Math.min(lo + 1, palette.length - 1);
        return lerpColor(palette[lo], palette[hi], f - lo);
    }

    const colors = new Array(BAR_COUNT);
    for (var i = 0; i < BAR_COUNT; i++) {
        colors[i] = barColor(i);
        phases[i] = i * 0.18 + Math.random() * 0.4;
        heights[i] = 0.05 + Math.random() * 0.15;
        targets[i] = heights[i];
    }

    var nextBeatAt   = 800 + Math.random() * 600;
    var beatAccum    = 0;
    var lastTime     = 0;

    function waveTarget(idx, time) {
        var t  = idx / BAR_COUNT;
        var p  = phases[idx];
        var w1 = 0.35 + 0.35 * Math.sin(t * Math.PI * 2.2 + time * 0.0006 + p);
        var w2 = 0.18 * Math.sin(t * Math.PI * 5.0 - time * 0.0012 + p * 1.7);
        var w3 = 0.08 * Math.sin(t * Math.PI * 11.0 + time * 0.003 + p * 2.3);
        var env = 0.8 + 0.2 * Math.sin(time * 0.0004 + p * 0.5);
        return Math.max(0.04, Math.min(1.0, (w1 + w2 + w3) * env));
    }

    function draw(time) {
        var w = canvas.width, h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        var dt = lastTime ? time - lastTime : 16;
        lastTime = time;

        beatAccum += dt;
        if (beatAccum >= nextBeatAt) {
            beatAccum  = 0;
            nextBeatAt = 700 + Math.random() * 900;
            var centre = Math.random() * BAR_COUNT;
            var spread = 6 + Math.random() * 10;
            for (var i = 0; i < BAR_COUNT; i++) {
                var dist = Math.abs(i - centre);
                if (dist < spread) {
                    var boost = (1.0 - dist / spread);
                    boost *= boost;
                    targets[i] = Math.min(1.0, targets[i] + boost * (0.5 + Math.random() * 0.35));
                    velocities[i] += boost * 0.06;
                }
            }
        }

        for (var i = 0; i < BAR_COUNT; i++) {
            var wt = waveTarget(i, time);
            targets[i] += (wt - targets[i]) * 0.045;
        }

        for (var i = 0; i < BAR_COUNT; i++) {
            var diff = targets[i] - heights[i];
            velocities[i] += diff * SPRING;
            velocities[i] *= DAMPING;
            heights[i]    += velocities[i];
            if (heights[i] < 0.02)  { heights[i] = 0.02;  velocities[i] *= -0.3; }
            if (heights[i] > 1.0)   { heights[i] = 1.0;   velocities[i] *= -0.2; }
        }

        var totalGap  = GAP * (BAR_COUNT - 1);
        var barW      = (w - totalGap) / BAR_COUNT;
        var yFloor    = h * FLOOR_Y;
        var maxBarH   = h * MAX_H_FRAC;
        var radius    = Math.min(barW * 0.5, 5);

        for (var i = 0; i < BAR_COUNT; i++) {
            var x    = i * (barW + GAP);
            var barH = heights[i] * maxBarH;
            if (barH < 1) barH = 1;
            var yTop = yFloor - barH;
            var c    = colors[i];
            var cr   = c[0] | 0, cg = c[1] | 0, cb = c[2] | 0;

            var grad = ctx.createLinearGradient(x, yFloor, x, yTop);
            grad.addColorStop(0, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.95)');
            grad.addColorStop(0.5, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.75)');
            grad.addColorStop(1, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.35)');

            ctx.shadowColor = 'rgba(' + cr + ',' + cg + ',' + cb + ',0.55)';
            ctx.shadowBlur  = 14 + heights[i] * 10;

            ctx.beginPath();
            ctx.moveTo(x, yFloor);
            ctx.lineTo(x, yTop + radius);
            ctx.quadraticCurveTo(x, yTop, x + radius, yTop);
            ctx.lineTo(x + barW - radius, yTop);
            ctx.quadraticCurveTo(x + barW, yTop, x + barW, yTop + radius);
            ctx.lineTo(x + barW, yFloor);
            ctx.closePath();
            ctx.fillStyle = grad;
            ctx.fill();

            ctx.shadowBlur = 0;
            ctx.beginPath();
            ctx.moveTo(x + radius, yTop);
            ctx.lineTo(x + barW - radius, yTop);
            ctx.strokeStyle = 'rgba(255,255,255,' + (0.12 + heights[i] * 0.15) + ')';
            ctx.lineWidth   = 1;
            ctx.stroke();

            var reflH = barH * REFL_FRAC;
            var reflGrad = ctx.createLinearGradient(x, yFloor, x, yFloor + reflH);
            reflGrad.addColorStop(0, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.12)');
            reflGrad.addColorStop(0.6, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.03)');
            reflGrad.addColorStop(1, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.0)');
            ctx.fillStyle = reflGrad;
            ctx.fillRect(x, yFloor + 1, barW, reflH);
        }

        ctx.shadowBlur = 0;
        ctx.beginPath();
        ctx.moveTo(0, yFloor + 0.5);
        ctx.lineTo(w, yFloor + 0.5);
        ctx.strokeStyle = 'rgba(255,255,255,0.06)';
        ctx.lineWidth   = 1;
        ctx.stroke();

        animId = requestAnimationFrame(draw);
    }
    animId = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animId);
};

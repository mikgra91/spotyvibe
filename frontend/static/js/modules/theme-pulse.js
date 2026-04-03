import { THEME_RENDERERS } from './theme-switcher.js';

THEME_RENDERERS.pulse = function(canvas) {
    // Bail out if user prefers reduced motion
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        return () => {};
    }

    const ctx = canvas.getContext('2d');
    let animId;
    let stopped = false;

    const isMobile = window.innerWidth <= 768;

    const COLORS = [
        [30, 215, 96],
        [25, 211, 197],
        [76, 168, 255],
        [140, 61, 255],
        [177, 77, 255],
        [255, 77, 184]
    ];

    const EMITTER_COUNT = isMobile ? 3 : 5;
    const emitters = [];
    function initEmitters() {
        emitters.length = 0;
        const w = canvas.width, h = canvas.height;
        for (let i = 0; i < EMITTER_COUNT; i++) {
            emitters.push({
                x: w * (0.15 + Math.random() * 0.7),
                y: h * (0.15 + Math.random() * 0.7),
                depth: 0.3 + Math.random() * 0.7,
                colorIdx: Math.floor(Math.random() * COLORS.length),
                nextSpawn: 0,
                interval: 1200 + Math.random() * 2000
            });
        }
    }
    initEmitters();

    const MAX_RINGS = isMobile ? 40 : 120;
    const ringPool = [];
    let ringCount = 0;
    for (let i = 0; i < MAX_RINGS; i++) {
        ringPool.push({
            active: false, x: 0, y: 0, r: 0, maxR: 0,
            speed: 0, color: COLORS[0], life: 0,
            lineWidth: 2, soft: false, intensity: 1
        });
    }
    function acquireRing() {
        for (let i = 0; i < MAX_RINGS; i++) {
            if (!ringPool[i].active) { ringCount++; return ringPool[i]; }
        }
        return null;
    }
    function releaseRing(ring) { ring.active = false; ringCount--; }

    function spawnRing(ex, ey, depth, colorIdx, intense) {
        const ring = acquireRing();
        if (!ring) return;
        const c = COLORS[colorIdx % COLORS.length];
        const depthScale = 0.4 + depth * 0.6;
        ring.active = true;
        ring.x = ex + (Math.random() - 0.5) * 30;
        ring.y = ey + (Math.random() - 0.5) * 30;
        ring.r = 0;
        ring.maxR = (180 + Math.random() * 350) * depthScale;
        ring.speed = (0.25 + Math.random() * 0.55) * depthScale;
        ring.color = c;
        ring.life = 1;
        ring.intensity = intense ? 1.6 : 1;
        if (Math.random() < 0.35) {
            ring.lineWidth = 4 + Math.random() * 6;
            ring.soft = true;
        } else {
            ring.lineWidth = 0.8 + Math.random() * 1.8;
            ring.soft = false;
        }
    }

    const MAX_PARTICLES = isMobile ? 20 : 60;
    const particles = [];
    function initParticles() {
        particles.length = 0;
        for (let i = 0; i < MAX_PARTICLES; i++) {
            particles.push({
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height,
                vx: (Math.random() - 0.5) * 0.3,
                vy: -0.1 - Math.random() * 0.25,
                size: 1 + Math.random() * 2.5,
                alpha: 0.08 + Math.random() * 0.18,
                color: COLORS[Math.floor(Math.random() * COLORS.length)]
            });
        }
    }
    initParticles();

    let nextDrop = 4000 + Math.random() * 6000;
    let dropFlash = 0;
    let lastTime = 0;
    let breathPhase = 0;

    function draw(time) {
        if (stopped) return;

        // Pause when tab/app is backgrounded
        if (document.visibilityState === 'hidden') {
            animId = requestAnimationFrame(draw);
            return;
        }

        const dt = lastTime ? (time - lastTime) : 16;
        lastTime = time;

        const W = canvas.width, H = canvas.height;
        ctx.clearRect(0, 0, W, H);

        breathPhase += dt * 0.0004;
        const cx = W * 0.5, cy = H * 0.5;
        const breathVal = 0.5 + 0.5 * Math.sin(breathPhase);
        const ambR = 220 + breathVal * 120 + dropFlash * 80;
        const ambAlpha = 0.045 + breathVal * 0.035 + dropFlash * 0.06;
        const amb = ctx.createRadialGradient(cx, cy, 0, cx, cy, ambR);
        amb.addColorStop(0, `rgba(30,215,96,${(ambAlpha * 1.2).toFixed(3)})`);
        amb.addColorStop(0.35, `rgba(25,211,197,${(ambAlpha * 0.7).toFixed(3)})`);
        amb.addColorStop(0.65, `rgba(140,61,255,${(ambAlpha * 0.5).toFixed(3)})`);
        amb.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = amb;
        ctx.beginPath();
        ctx.arc(cx, cy, ambR, 0, Math.PI * 2);
        ctx.fill();

        nextDrop -= dt;
        if (dropFlash > 0) dropFlash = Math.max(0, dropFlash - dt * 0.003);
        if (nextDrop <= 0) {
            dropFlash = 1;
            const burstCount = 2 + Math.floor(Math.random() * 2);
            for (let b = 0; b < burstCount; b++) {
                const em = emitters[Math.floor(Math.random() * emitters.length)];
                const numRings = 3 + Math.floor(Math.random() * 4);
                for (let j = 0; j < numRings; j++) {
                    spawnRing(em.x, em.y, em.depth, em.colorIdx + j, true);
                }
            }
            nextDrop = 5000 + Math.random() * 8000;
        }

        for (let e = 0; e < emitters.length; e++) {
            const em = emitters[e];
            em.nextSpawn -= dt;
            if (em.nextSpawn <= 0) {
                const n = Math.random() < 0.3 ? 2 : 1;
                for (let j = 0; j < n; j++) {
                    spawnRing(em.x, em.y, em.depth, em.colorIdx + j, false);
                }
                em.nextSpawn = em.interval * (0.8 + Math.random() * 0.4);
            }
            em.x += (Math.random() - 0.5) * 0.15;
            em.y += (Math.random() - 0.5) * 0.15;
            em.x = Math.max(W * 0.05, Math.min(W * 0.95, em.x));
            em.y = Math.max(H * 0.05, Math.min(H * 0.95, em.y));
        }

        for (let i = 0; i < MAX_RINGS; i++) {
            const ring = ringPool[i];
            if (!ring.active) continue;

            ring.r += ring.speed * (dt * 0.06);
            ring.life = 1 - ring.r / ring.maxR;
            if (ring.life <= 0) { releaseRing(ring); continue; }

            const [r, g, b] = ring.color;
            const a = ring.life * ring.intensity;
            const ea = Math.min(a, 1);

            if (ring.soft && ring.r > 5) {
                const inner = Math.max(0, ring.r - ring.lineWidth * 3);
                const grad = ctx.createRadialGradient(
                    ring.x, ring.y, inner,
                    ring.x, ring.y, ring.r + ring.lineWidth * 2
                );
                grad.addColorStop(0, `rgba(${r},${g},${b},0)`);
                grad.addColorStop(0.5, `rgba(${r},${g},${b},${(0.07 * ea).toFixed(3)})`);
                grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
                ctx.fillStyle = grad;
                ctx.beginPath();
                ctx.arc(ring.x, ring.y, ring.r + ring.lineWidth * 2, 0, Math.PI * 2);
                ctx.fill();
            }

            ctx.beginPath();
            ctx.arc(ring.x, ring.y, ring.r, 0, Math.PI * 2);
            const strokeA = (ring.soft ? 0.2 : 0.4) * ea;
            ctx.strokeStyle = `rgba(${r},${g},${b},${strokeA.toFixed(3)})`;
            ctx.lineWidth = ring.lineWidth * (ring.soft ? ring.life : 1);

            if (!isMobile) {
                if (ring.soft) {
                    ctx.shadowColor = `rgba(${r},${g},${b},${(0.45 * ea).toFixed(3)})`;
                    ctx.shadowBlur = 18 + ring.lineWidth * 2;
                } else {
                    ctx.shadowColor = `rgba(${r},${g},${b},${(0.3 * ea).toFixed(3)})`;
                    ctx.shadowBlur = 8;
                }
            }
            ctx.stroke();
            ctx.shadowBlur = 0;
        }

        for (let i = 0; i < MAX_PARTICLES; i++) {
            const p = particles[i];
            p.x += p.vx * (dt * 0.06);
            p.y += p.vy * (dt * 0.06);
            if (p.x < -10) p.x = W + 10;
            if (p.x > W + 10) p.x = -10;
            if (p.y < -10) { p.y = H + 10; p.x = Math.random() * W; }

            const [pr, pg, pb] = p.color;
            const pa = p.alpha + dropFlash * 0.12;
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${pr},${pg},${pb},${pa.toFixed(3)})`;
            if (!isMobile) {
                ctx.shadowColor = `rgba(${pr},${pg},${pb},${(pa * 0.6).toFixed(3)})`;
                ctx.shadowBlur = 6;
            }
            ctx.fill();
            ctx.shadowBlur = 0;
        }

        const vig = ctx.createRadialGradient(cx, cy, W * 0.2, cx, cy, W * 0.75);
        vig.addColorStop(0, 'rgba(0,0,0,0)');
        vig.addColorStop(1, 'rgba(0,0,0,0.15)');
        ctx.fillStyle = vig;
        ctx.fillRect(0, 0, W, H);

        if (isMobile) {
            // Throttle to ~30fps on mobile
            setTimeout(() => { animId = requestAnimationFrame(draw); }, 17);
        } else {
            animId = requestAnimationFrame(draw);
        }
    }

    for (let e = 0; e < emitters.length; e++) {
        const em = emitters[e];
        for (let j = 0; j < 3; j++) {
            spawnRing(em.x, em.y, em.depth, em.colorIdx + j, false);
        }
    }
    animId = requestAnimationFrame(draw);
    return () => { stopped = true; cancelAnimationFrame(animId); };
};

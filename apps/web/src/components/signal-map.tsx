"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { MapIsland, MapPoint } from "@/lib/api";
import { categoryLabel } from "@/lib/format";
import { sourceName } from "@/lib/sources";

/**
 * The week's stories (green) and reported problems (amber) as a radar: positions come from the
 * API's t-SNE layout of their embeddings, so nearby dots are about similar things. A sweep
 * brightens what it passes; hovering draws lines to the nearest dots in meaning.
 */

const STORY = [57, 255, 127];
const PROBLEM = [255, 181, 71];
const NEIGHBOURS = 6;

type View = { scale: number; tx: number; ty: number };

function sprite([r, g, b]: number[]): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const ctx = c.getContext("2d")!;
  const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, `rgba(255,255,255,1)`);
  grad.addColorStop(0.12, `rgba(${r},${g},${b},1)`);
  grad.addColorStop(0.35, `rgba(${r},${g},${b},0.35)`);
  grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 64, 64);
  return c;
}

function describe(p: MapPoint) {
  return p.kind === "story" ? sourceName(p.meta) : categoryLabel(p.meta as Parameters<typeof categoryLabel>[0]);
}

export function SignalMap({
  points,
  islands,
  mode = "full",
  className = "",
}: {
  points: MapPoint[];
  islands: MapIsland[];
  mode?: "full" | "hero";
  className?: string;
}) {
  const router = useRouter();
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const view = useRef<View>({ scale: 1, tx: 0, ty: 0 });
  const redraw = useRef<() => void>(() => {});
  const [hover, setHover] = useState<{ p: MapPoint; x: number; y: number; w: number } | null>(null);
  const [showStories, setShowStories] = useState(true);
  const [showProblems, setShowProblems] = useState(true);
  const [query, setQuery] = useState("");
  const interactive = mode === "full";

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? new Set(points.filter((p) => p.title.toLowerCase().includes(q)).map((p) => p)) : null;
  }, [points, query]);
  const visible = useMemo(
    () => points.filter((p) => (p.kind === "story" ? showStories : showProblems)),
    [points, showStories, showProblems],
  );
  const labelled = useMemo(
    () => [...islands].sort((a, b) => b.size - a.size).slice(0, mode === "hero" ? 4 : islands.length),
    [islands, mode],
  );

  // Mutable state the animation loop reads without re-rendering.
  const live = useRef({ visible, matches, hover: null as MapPoint | null, labelled });
  useEffect(() => {
    live.current = { visible, matches, hover: hover?.p ?? null, labelled };
    redraw.current();
  }, [visible, matches, hover, labelled]);

  useEffect(() => {
    const el = canvas.current!;
    const box = wrap.current!;
    const ctx = el.getContext("2d")!;
    const sprites = { story: sprite(STORY), problem: sprite(PROBLEM) };
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const started = performance.now();
    let w = 0;
    let h = 0;
    let raf = 0;
    let onScreen = true;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = box.clientWidth;
      h = box.clientHeight;
      el.width = Math.round(w * dpr);
      el.height = Math.round(h * dpr);
      el.style.width = `${w}px`;
      el.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw(performance.now());
    };

    const project = (x: number, y: number, t: number) => {
      const r = Math.min(w, h) * 0.46 * view.current.scale;
      const grow = reduce ? 1 : 1 - Math.pow(1 - Math.min(1, (t - started) / 1400), 3);
      return [w / 2 + view.current.tx + x * r * grow, h / 2 + view.current.ty - y * r * grow];
    };

    function draw(t: number) {
      const { visible, matches, hover, labelled } = live.current;
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2 + view.current.tx;
      const cy = h / 2 + view.current.ty;
      const R = Math.min(w, h) * 0.46 * view.current.scale;

      // Radar rings and crosshair.
      ctx.strokeStyle = "rgba(57,255,127,0.08)";
      ctx.lineWidth = 1;
      for (let k = 1; k <= 4; k++) {
        ctx.beginPath();
        ctx.arc(cx, cy, (R * k) / 4, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.moveTo(cx - R, cy);
      ctx.lineTo(cx + R, cy);
      ctx.moveTo(cx, cy - R);
      ctx.lineTo(cx, cy + R);
      ctx.stroke();

      // The sweep: a rotating wedge; dots just behind it light up.
      const sweep = reduce ? -Math.PI / 4 : ((t - started) / 6000) * Math.PI * 2;
      if (!reduce) {
        const grad = ctx.createConicGradient(sweep - 0.6, cx, cy);
        grad.addColorStop(0, "rgba(57,255,127,0)");
        grad.addColorStop(0.095, "rgba(57,255,127,0.10)");
        grad.addColorStop(0.0955, "rgba(57,255,127,0)");
        grad.addColorStop(1, "rgba(57,255,127,0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, R, 0, Math.PI * 2);
        ctx.fill();
      }

      // Neighbour lines for the hovered dot.
      if (hover) {
        const near = [...visible]
          .filter((p) => p !== hover)
          .sort((a, b) => (a.x - hover.x) ** 2 + (a.y - hover.y) ** 2 - ((b.x - hover.x) ** 2 + (b.y - hover.y) ** 2))
          .slice(0, NEIGHBOURS);
        const [hx, hy] = project(hover.x, hover.y, t);
        ctx.strokeStyle = "rgba(179,255,203,0.45)";
        ctx.lineWidth = 1;
        for (const n of near) {
          const [nx, ny] = project(n.x, n.y, t);
          ctx.beginPath();
          ctx.moveTo(hx, hy);
          ctx.lineTo(nx, ny);
          ctx.stroke();
        }
      }

      ctx.globalCompositeOperation = "lighter";
      // Nebula: a wide, faint halo per dot, so dense topics glow as clouds.
      const halo = 70 * Math.sqrt(view.current.scale);
      ctx.globalAlpha = 0.035;
      for (const p of visible) {
        const [x, y] = project(p.x, p.y, t);
        ctx.drawImage(sprites[p.kind], x - halo / 2, y - halo / 2, halo, halo);
      }
      for (const p of visible) {
        const [x, y] = project(p.x, p.y, t);
        if (x < -20 || y < -20 || x > w + 20 || y > h + 20) continue;
        const angle = Math.atan2(-(y - cy), x - cx);
        const behind = (((sweep - (-angle)) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
        const lit = reduce ? 0 : Math.max(0, 1 - behind / 1.2);
        const dim = matches && !matches.has(p) ? 0.12 : 1;
        const base = 9 + p.weight * 18;
        const size = (p === hover ? base * 1.9 : base) * (1 + lit * 0.5) * Math.sqrt(view.current.scale);
        ctx.globalAlpha = Math.min(1, (0.6 + p.weight * 0.4 + lit * 0.6) * dim);
        ctx.drawImage(sprites[p.kind], x - size / 2, y - size / 2, size, size);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";

      // Island labels.
      ctx.font = "600 11px var(--font-jetbrains), ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (const isl of labelled) {
        const [px, py] = project(isl.x, isl.y, t);
        const text = isl.label.toUpperCase();
        const tw = ctx.measureText(text).width + 14;
        // Keep labels inside the canvas, even in the narrow home-page hero.
        const x = Math.min(Math.max(px, tw / 2 + 4), w - tw / 2 - 4);
        const y = Math.min(Math.max(py, 14), h - 14);
        ctx.fillStyle = "rgba(0,0,0,0.62)";
        ctx.beginPath();
        ctx.roundRect(x - tw / 2, y - 10, tw, 20, 10);
        ctx.fill();
        ctx.fillStyle = "rgba(198,220,205,0.92)";
        ctx.fillText(text, x, y);
      }
    }
    redraw.current = () => draw(performance.now());

    const loop = (t: number) => {
      if (onScreen && !document.hidden) draw(t);
      raf = requestAnimationFrame(loop);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(box);
    const io = new IntersectionObserver(([e]) => (onScreen = e.isIntersecting));
    io.observe(box);
    resize();
    if (reduce) draw(performance.now());
    else raf = requestAnimationFrame(loop);

    // Pointer: hover, click, drag to pan (full mode), wheel/pinch to zoom (full mode).
    const pointers = new Map<number, { x: number; y: number }>();
    let moved = 0;
    let pinch = 0;
    const local = (e: PointerEvent | WheelEvent) => {
      const r = el.getBoundingClientRect();
      return [e.clientX - r.left, e.clientY - r.top];
    };
    const nearest = (mx: number, my: number) => {
      let best: MapPoint | null = null;
      let bestD = 16 * 16;
      for (const p of live.current.visible) {
        const [x, y] = project(p.x, p.y, performance.now() + 1e6);
        const d = (x - mx) ** 2 + (y - my) ** 2;
        if (d < bestD) {
          bestD = d;
          best = p;
        }
      }
      return best;
    };
    const zoomAt = (mx: number, my: number, factor: number) => {
      const v = view.current;
      const next = Math.min(10, Math.max(0.7, v.scale * factor));
      const f = next / v.scale;
      v.tx = mx - w / 2 - (mx - w / 2 - v.tx) * f;
      v.ty = my - h / 2 - (my - h / 2 - v.ty) * f;
      v.scale = next;
      if (reduce) draw(performance.now());
    };
    const onDown = (e: PointerEvent) => {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      moved = 0;
      if (interactive) el.setPointerCapture(e.pointerId);
    };
    const onMove = (e: PointerEvent) => {
      const [mx, my] = local(e);
      const prev = pointers.get(e.pointerId);
      if (interactive && prev) {
        if (pointers.size === 2) {
          const [a, b] = [...pointers.values()];
          const before = Math.hypot(a.x - b.x, a.y - b.y);
          pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
          const [c, d] = [...pointers.values()];
          const after = Math.hypot(c.x - d.x, c.y - d.y);
          if (pinch && before > 0) zoomAt(mx, my, after / before);
          pinch = 1;
          moved += 10;
          return;
        }
        view.current.tx += e.clientX - prev.x;
        view.current.ty += e.clientY - prev.y;
        moved += Math.abs(e.clientX - prev.x) + Math.abs(e.clientY - prev.y);
        pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (reduce) draw(performance.now());
        if (moved > 4) return setHover(null);
      }
      const p = nearest(mx, my);
      setHover(p ? { p, x: mx, y: my, w } : null);
      el.style.cursor = p ? "pointer" : interactive ? "grab" : "default";
      if (reduce) requestAnimationFrame(() => draw(performance.now()));
    };
    const onUp = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      pinch = 0;
      if (moved > 4) return;
      const [mx, my] = local(e);
      const p = nearest(mx, my);
      if (p) router.push(p.kind === "story" ? `/stories/${p.id}` : `/problems/${p.id}`);
    };
    const onLeave = () => setHover(null);
    const onWheel = (e: WheelEvent) => {
      if (!interactive) return;
      e.preventDefault();
      const [mx, my] = local(e);
      zoomAt(mx, my, Math.exp(-e.deltaY * 0.0015));
    };
    const onDouble = () => {
      if (!interactive) return;
      view.current = { scale: 1, tx: 0, ty: 0 };
      if (reduce) draw(performance.now());
    };
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointerleave", onLeave);
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("dblclick", onDouble);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointerleave", onLeave);
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("dblclick", onDouble);
    };
  }, [interactive, router]);

  const stories = points.filter((p) => p.kind === "story").length;
  return (
    <div ref={wrap} className={`relative overflow-hidden ${className}`} data-signal-map>
      <canvas
        ref={canvas}
        role="img"
        aria-label={`Map of ${stories} stories and ${points.length - stories} reported problems, placed by meaning`}
        className="absolute inset-0 touch-none"
      />
      {interactive && (
        <div className="absolute top-3 left-3 flex flex-wrap items-center gap-2 rounded-xl border hairline bg-black/70 p-2 backdrop-blur">
          <button
            type="button"
            aria-pressed={showStories}
            onClick={() => setShowStories((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${showStories ? "bg-signal-400/15 text-signal-400" : "text-fg-500"}`}
          >
            <span className="h-2 w-2 rounded-full bg-signal-400 shadow-[0_0_8px_rgb(57_255_127)]" /> Stories
          </button>
          <button
            type="button"
            aria-pressed={showProblems}
            onClick={() => setShowProblems((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${showProblems ? "bg-amber-400/15 text-amber-300" : "text-fg-500"}`}
          >
            <span className="h-2 w-2 rounded-full bg-amber-400 shadow-[0_0_8px_rgb(255_181_71)]" /> Problems
          </button>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Highlight… (e.g. vllm)"
            aria-label="Highlight dots whose title contains"
            className="h-7 w-44 rounded-full border hairline bg-field-950 px-3 text-xs text-fg-50 placeholder:text-fg-600 focus:border-signal-400 focus:outline-none"
          />
          {matches && <span className="px-1 font-mono text-[11px] text-fg-400">{matches.size} match</span>}
        </div>
      )}
      {interactive && (
        <p className="pointer-events-none absolute bottom-3 left-3 font-mono text-[11px] text-fg-600">
          scroll to zoom · drag to pan · double-click to reset · click a dot to open
        </p>
      )}
      {hover && (
        <div
          className="pointer-events-none absolute z-10 max-w-xs rounded-lg border hairline bg-black/85 p-3 text-xs shadow-2xl backdrop-blur"
          style={{
            left: Math.max(8, Math.min(hover.x + 14, hover.w - 300)),
            top: Math.max(8, hover.y - 10),
          }}
        >
          <p className={`font-mono text-[10px] font-semibold uppercase ${hover.p.kind === "story" ? "text-signal-400" : "text-amber-300"}`}>
            {hover.p.kind === "story" ? "Story" : "Problem"} · {describe(hover.p)}
          </p>
          <p className="mt-1 text-[13px] leading-snug text-fg-50">{hover.p.title}</p>
          <p className="mt-1.5 text-[10px] text-fg-500">Lines point to the nearest dots in meaning. Click to open.</p>
        </div>
      )}
    </div>
  );
}

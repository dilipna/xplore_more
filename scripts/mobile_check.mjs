// Phone-width check of the running web app over the Chrome DevTools Protocol (no npm deps).
//   node scripts/mobile_check.mjs [base_url] [out_dir]     default: http://localhost:3100  .data/shots
// Emulates a 390x844 phone (DPR 2, mobile), reports any horizontal overflow per page (the
// element sticking out furthest), and saves a full-page screenshot. Plain --window-size can't
// do this: Chrome clamps windows to ~500 px, so a "390 px" shot is really a crop of 500.
// Exit code 1 if any page overflows. Needs Node >= 22 (global WebSocket) and Chrome or Edge.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const BASE = process.argv[2] ?? "http://localhost:3100";
const OUT = process.argv[3] ?? ".data/shots";
const PAGES = (process.env.PAGES ?? "/ /problems/1526 /search?q=kubernetes /feed /how-it-works")
  .split(/\s+/)
  .filter(Boolean);
const PORT = 9333;
const CHROME =
  process.env.CHROME ??
  [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ].find((p) => existsSync(p));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  if (!CHROME) throw new Error("no Chrome/Edge found; set CHROME");
  mkdirSync(OUT, { recursive: true });
  const profile = join(process.env.TEMP ?? "/tmp", `xm-mobile-check-${process.pid}`);
  const chrome = spawn(CHROME, [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`,
    "about:blank",
  ]);
  try {
    let target;
    for (let i = 0; i < 50 && !target; i++) {
      try {
        const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
        target = list.find((t) => t.type === "page");
      } catch {
        await sleep(200);
      }
    }
    if (!target) throw new Error("Chrome DevTools endpoint did not come up");

    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((r, j) => ((ws.onopen = r), (ws.onerror = j)));
    let seq = 0;
    const pending = new Map();
    const waiters = [];
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && pending.has(msg.id)) {
        const { resolve, reject } = pending.get(msg.id);
        pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      } else if (msg.method) {
        waiters.filter((w) => w.method === msg.method).forEach((w) => w.resolve(msg.params));
      }
    };
    const send = (method, params = {}) =>
      new Promise((resolve, reject) => {
        const id = ++seq;
        pending.set(id, { resolve, reject });
        ws.send(JSON.stringify({ id, method, params }));
      });
    const once = (method) =>
      new Promise((resolve) => {
        const w = { method, resolve: (p) => (waiters.splice(waiters.indexOf(w), 1), resolve(p)) };
        waiters.push(w);
      });

    await send("Page.enable");
    await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
    // Reduced motion: count-ups render their final (real) values, so screenshots never catch them mid-way.
    await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });

    let failures = 0;
    for (const page of PAGES) {
      const loaded = once("Page.loadEventFired");
      const nav = await send("Page.navigate", { url: BASE + page });
      await loaded;
      if (nav.errorText) {
        // Chrome's own error page never overflows, so an unreachable app must not pass as "ok".
        failures++;
        console.log(`UNREACH  ${page}  ${nav.errorText}`);
        continue;
      }
      await sleep(500);
      const { result } = await send("Runtime.evaluate", {
        returnByValue: true,
        expression: `(() => {
          const vw = document.documentElement.clientWidth;
          let worst = null;
          for (const el of document.querySelectorAll("body *")) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            // Skip content inside horizontally scrollable containers: that overflow is intended.
            let p = el.parentElement, scrolls = false;
            while (p && p !== document.body) {
              const ox = getComputedStyle(p).overflowX;
              if (ox === "auto" || ox === "scroll" || ox === "hidden") { scrolls = true; break; }
              p = p.parentElement;
            }
            if (scrolls) continue;
            if (r.right > vw + 1 && (!worst || r.right > worst.right))
              worst = { right: Math.round(r.right), tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 80), text: (el.textContent || "").trim().slice(0, 60) };
          }
          return { vw, scrollWidth: document.documentElement.scrollWidth, worst };
        })()`,
      });
      const v = result.value;
      const overflow = v.scrollWidth > v.vw || v.worst;
      if (overflow) failures++;
      console.log(
        `${overflow ? "OVERFLOW" : "ok      "} ${page}  viewport=${v.vw} scrollWidth=${v.scrollWidth}` +
          (v.worst ? `  worst: <${v.worst.tag} class="${v.worst.cls}"> right=${v.worst.right} "${v.worst.text}"` : ""),
      );
      const { data } = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
      const name = page.replace(/^\//, "").replace(/%20/g, "_").replace(/[/?=&]/g, "_") || "home";
      writeFileSync(join(OUT, `${name}-mobile.png`), Buffer.from(data, "base64"));
    }
    ws.close();
    process.exitCode = failures ? 1 : 0;
  } finally {
    chrome.kill();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});

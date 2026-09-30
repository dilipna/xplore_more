// Browser flow check of the running web app over the Chrome DevTools Protocol (no npm deps):
// the parts that only work with JavaScript in a real browser.
//   node scripts/flow_check.mjs [base_url]        default: http://localhost:3100
// 1. Follow a topic from search, see it on My topics, unfollow it (localStorage only).
// 2. Move a ranking slider on /feed and see the URL and the page re-rank.
// 3. Keyboard shortcuts (j, ?, Escape).
// Exit code 1 on the first failed step. Needs Node >= 22 and Chrome or Edge.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const BASE = process.argv[2] ?? "http://localhost:3100";
const PORT = 9334;
const CHROME =
  process.env.CHROME ??
  [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ].find((p) => existsSync(p));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const target = list.find((t) => t.type === "page");
      if (target) return target;
    } catch {
      await sleep(200);
    }
  }
  throw new Error("Chrome DevTools endpoint did not come up");
}

async function main() {
  if (!CHROME) throw new Error("no Chrome/Edge found; set CHROME");
  const profile = join(process.env.TEMP ?? "/tmp", `xm-flow-check-${process.pid}`);
  const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "about:blank"]);
  let failed = false;
  try {
    const ws = new WebSocket((await connect()).webSocketDebuggerUrl);
    await new Promise((r, j) => ((ws.onopen = r), (ws.onerror = j)));
    let seq = 0;
    const pending = new Map();
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && pending.has(msg.id)) {
        const { resolve, reject } = pending.get(msg.id);
        pending.delete(msg.id);
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
      }
    };
    const send = (method, params = {}) =>
      new Promise((resolve, reject) => {
        const id = ++seq;
        pending.set(id, { resolve, reject });
        ws.send(JSON.stringify({ id, method, params }));
      });
    const js = async (expression) =>
      (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result.value;
    const go = async (path) => {
      await send("Page.navigate", { url: BASE + path });
      await sleep(2500);
    };
    // Poll up to ~8 s: client redirects and server re-renders take a moment.
    const until = async (expression) => {
      for (let i = 0; i < 16; i++) {
        if (await js(expression)) return true;
        await sleep(500);
      }
      return false;
    };
    const step = (name, ok) => {
      console.log(`${ok ? "ok  " : "FAIL"}  ${name}`);
      if (!ok) failed = true;
      return ok;
    };
    const clickText = (text) =>
      js(`(() => { const b = [...document.querySelectorAll("button")].find(b => b.textContent.trim() === ${JSON.stringify(text)}); if (!b) return false; b.click(); return true; })()`);

    await send("Page.enable");
    await send("Runtime.enable");

    // 1. Follow a topic, see it on My topics, unfollow it.
    await go("/search?q=vllm");
    step("search page shows a Follow button", await until(`[...document.querySelectorAll("button")].some(b => b.textContent.trim() === "Follow")`));
    step("clicking Follow stores the topic in this browser", (await clickText("Follow")) && (await until(`(localStorage.getItem("xm:follows:v1") || "").includes("vllm")`)));
    step("button now says Following", await until(`[...document.querySelectorAll("button")].some(b => b.textContent.trim() === "Following")`));
    await go("/topics");
    step("My topics loads the follow into the URL", await until(`location.search.includes("t=vllm")`));
    step("My topics lists vllm stories", await until(`document.querySelectorAll("section[aria-labelledby^=topic-] article").length > 0`));
    step("Unfollow empties My topics", (await clickText("Unfollow")) && (await until(`document.body.innerText.includes("don't follow any topics") || document.body.innerText.includes("don’t follow any topics")`)));
    step("storage is empty again", await until(`(localStorage.getItem("xm:follows:v1") || "[]") === "[]"`));
    // A previous visit long ago: every story listed is newer than it, so each gets the marker.
    await js(`localStorage.setItem("xm:follows:v1", '["kubernetes"]'); localStorage.setItem("xm:topics:last-visit", "1"); sessionStorage.clear(); true`);
    await go("/topics");
    step("stories newer than the last visit are marked", await until(`document.body.innerText.includes("New since your last visit")`));
    await js(`localStorage.clear(); sessionStorage.clear(); true`);

    // 2. Move the coverage slider; the URL and the ranking follow.
    await go("/feed");
    const moved = await js(`(() => {
      const input = document.querySelector('input[type=range]');
      if (!input) return false;
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      set.call(input, "3");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    })()`);
    step("slider move updates the URL", moved && (await until(`location.search.includes("w_sources=3")`)));
    step("re-ranked page shows rank changes", await until(`document.body.innerText.includes("Custom weights") && /[▲▼]/.test(document.body.innerText)`));
    step("Reset returns to the default URL", (await clickText("Reset to default")) && (await until(`!location.search.includes("w_sources")`)));
    // 3. Keyboard shortcuts: j selects the first card, ? opens the help, Escape closes it.
    const key = async (k) => {
      await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, text: k.length === 1 ? k : undefined });
      await send("Input.dispatchKeyEvent", { type: "keyUp", key: k });
    };
    await go("/");
    await key("j");
    step("j selects a card", await until(`!!document.querySelector("main article[data-kb-selected]")`));
    await key("?");
    step("? opens the shortcut help", await until(`document.body.innerText.includes("Keyboard shortcuts")`));
    await key("Escape");
    step("Escape closes it", await until(`!document.querySelector('[role=dialog]')`));
    ws.close();
  } finally {
    chrome.kill();
  }
  console.log(failed ? "FLOW CHECK FAILED" : "FLOW CHECK PASSED");
  process.exit(failed ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

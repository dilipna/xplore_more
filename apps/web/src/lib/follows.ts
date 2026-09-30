/**
 * Followed topics, kept only in this browser (localStorage). There is no account, and nothing
 * about the reader is stored on the server: the topics page receives them in its URL, like a
 * search, and forgets them after rendering.
 */

export const MAX_FOLLOWS = 8;
const KEY = "xm:follows:v1";
const VISIT_KEY = "xm:topics:last-visit";
const PREV_KEY = "xm:topics:prev-visit"; // sessionStorage: the visit before this one
const EVENT = "xm:follows";

export function normalizeTopic(q: string): string {
  return q.trim().replace(/\s+/g, " ").slice(0, 64);
}

export function readFollows(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((t): t is string => typeof t === "string").slice(0, MAX_FOLLOWS) : [];
  } catch {
    return [];
  }
}

function write(topics: string[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(topics.slice(0, MAX_FOLLOWS)));
  } catch {
    // Storage blocked (private mode, disabled site data): following just doesn't persist.
  }
  window.dispatchEvent(new Event(EVENT));
}

export function follow(topic: string): boolean {
  const t = normalizeTopic(topic);
  const current = readFollows();
  if (!t || current.includes(t)) return true;
  if (current.length >= MAX_FOLLOWS) return false;
  write([...current, t]);
  return true;
}

export function unfollow(topic: string) {
  write(readFollows().filter((t) => t !== normalizeTopic(topic)));
}

export function onFollowsChange(cb: () => void): () => void {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

/**
 * The previous visit to My topics, for "new since your last visit". The first call in a browser
 * session records now as the latest visit and remembers the one before it for the rest of the
 * session, so a refresh keeps the same markers.
 */
export function previousVisit(): number | null {
  try {
    const kept = sessionStorage.getItem(PREV_KEY);
    if (kept !== null) return kept === "" ? null : Number(kept);
    const last = localStorage.getItem(VISIT_KEY);
    sessionStorage.setItem(PREV_KEY, last ?? "");
    localStorage.setItem(VISIT_KEY, String(Date.now()));
    return last ? Number(last) : null;
  } catch {
    return null;
  }
}

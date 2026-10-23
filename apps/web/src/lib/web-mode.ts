/** Server-side explicit opt-in; a configured API URL alone cannot enable network calls. */
export function recordedMode(): boolean {
  return process.env.XM_WEB_MODE !== "connected";
}

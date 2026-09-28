/**
 * The system in two lanes: an event-driven ingest path (at-least-once delivery made
 * exactly-once by idempotency) and a serving path with no LLM anywhere in it.
 */

type Box = { x: number; y: number; w: number; title: string; lines: string[]; accent?: boolean; zone?: boolean };

const H = 92;

const INGEST: Box[] = [
  { x: 20, y: 70, w: 150, title: "48 sources", lines: ["43 tech feeds", "5 discussion APIs"] },
  { x: 200, y: 70, w: 150, title: "Go poller", lines: ["conditional GET", "per-host limits"] },
  { x: 380, y: 70, w: 120, title: "Pub/Sub", lines: ["discovered", "+ DLQ"] },
  { x: 530, y: 70, w: 170, title: "Go ingestor", lines: ["SSRF-safe fetch", "extract · text store"], zone: true },
  { x: 730, y: 70, w: 120, title: "Pub/Sub", lines: ["extracted", "+ DLQ"] },
  { x: 880, y: 70, w: 200, title: "Python indexer", lines: ["embed · dedupe", "cluster · classify"], accent: true },
];

const SERVE: Box[] = [
  { x: 880, y: 250, w: 200, title: "Postgres + pgvector", lines: ["FTS + HNSW halfvec", "problems · stories"] },
  { x: 610, y: 250, w: 230, title: "FastAPI", lines: ["hybrid search · demand rank", "keys · Redis limit + cache"], accent: true },
  { x: 380, y: 250, w: 190, title: "Web + MCP server", lines: ["this site", "find_problems tool"] },
  { x: 150, y: 250, w: 190, title: "Pro2Pro agents", lines: ["validate · build · ship", "LLMs live here"] },
];

function Node({ b }: { b: Box }) {
  return (
    <g>
      <rect
        x={b.x}
        y={b.y}
        width={b.w}
        height={H}
        rx={12}
        fill={b.accent ? "var(--color-signal-900)" : "var(--color-field-850)"}
        stroke={b.accent ? "var(--color-signal-500)" : "rgb(255 255 255 / 0.12)"}
        strokeDasharray={b.zone ? "5 4" : undefined}
      />
      <text x={b.x + 14} y={b.y + 30} fill="var(--color-fg-50)" fontSize="15" fontWeight="600">
        {b.title}
      </text>
      {b.lines.map((line, i) => (
        <text key={line} x={b.x + 14} y={b.y + 54 + i * 18} fill="var(--color-fg-400)" fontSize="12.5" fontFamily="var(--font-mono)">
          {line}
        </text>
      ))}
    </g>
  );
}

function Arrow({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }) {
  return (
    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--color-signal-500)" strokeWidth="1.6" markerEnd="url(#arrow)" opacity="0.85" />
  );
}

export function ArchitectureDiagram() {
  const mid = 70 + H / 2;
  const midServe = 250 + H / 2;
  return (
    <svg
      viewBox="0 0 1100 370"
      className="h-auto w-full"
      role="img"
      aria-label="Architecture: sources feed a Go poller, Pub/Sub and a Go ingestor, then a Python indexer writes to Postgres with pgvector; a FastAPI service serves the web app and an MCP server that Pro2Pro's agents call."
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-signal-500)" />
        </marker>
      </defs>

      <text x={20} y={40} fill="var(--color-fg-500)" fontSize="12" fontFamily="var(--font-mono)" letterSpacing="2">
        INGEST — EVENT-DRIVEN, AT-LEAST-ONCE DELIVERY, EXACTLY-ONCE EFFECTS
      </text>
      <text x={530} y={186} fill="var(--color-fg-600)" fontSize="11" fontFamily="var(--font-mono)">
        untrusted zone: no database access
      </text>
      <text x={20} y={224} fill="var(--color-fg-500)" fontSize="12" fontFamily="var(--font-mono)" letterSpacing="2">
        SERVE — NO LLM IN THIS PATH
      </text>

      {INGEST.map((b) => (
        <Node key={`${b.title}-${b.x}`} b={b} />
      ))}
      {SERVE.map((b) => (
        <Node key={`${b.title}-${b.x}`} b={b} />
      ))}

      <Arrow x1={170} y1={mid} x2={198} y2={mid} />
      <Arrow x1={350} y1={mid} x2={378} y2={mid} />
      <Arrow x1={500} y1={mid} x2={528} y2={mid} />
      <Arrow x1={700} y1={mid} x2={728} y2={mid} />
      <Arrow x1={850} y1={mid} x2={878} y2={mid} />
      <Arrow x1={980} y1={70 + H} x2={980} y2={248} />
      <Arrow x1={880} y1={midServe} x2={842} y2={midServe} />
      <Arrow x1={610} y1={midServe} x2={572} y2={midServe} />
      <Arrow x1={380} y1={midServe} x2={342} y2={midServe} />
    </svg>
  );
}

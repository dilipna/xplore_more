"use client";
import { useState } from "react";
import Link from "next/link";
import example from "@/data/brief-example.json";
import { parseBrief, downloadBrief, type Brief } from "@/lib/brief";

export default function BriefWorkbench({
  initial,
  loadError,
}: {
  initial: Brief | null;
  loadError: string;
}) {
  const [brief, setBrief] = useState<Brief | null>(initial),
    [error, setError] = useState(loadError),
    [notice, setNotice] = useState("");
  function patchSpec(field: "target_user" | "goal", value: string) {
    if (brief) {
      setBrief({ ...brief, spec: { ...brief.spec, [field]: value } });
      setNotice("");
    }
  }
  function patchList(field: "in_scope" | "out_of_scope", value: string) {
    if (brief) {
      setBrief({
        ...brief,
        spec: { ...brief.spec, [field]: value.split("\n") },
      });
      setNotice("");
    }
  }
  function patchCriterion(
    index: number,
    field: "given" | "when" | "then",
    value: string,
  ) {
    if (brief) {
      const acceptance = brief.spec.acceptance.map((c, i) =>
        i === index ? { ...c, [field]: value } : c,
      );
      setBrief({ ...brief, spec: { ...brief.spec, acceptance } });
      setNotice("");
    }
  }
  function exportDraft() {
    try {
      if (!brief) throw new Error("Select a problem first.");
      const valid = parseBrief(JSON.stringify(brief));
      downloadBrief(valid);
      setError("");
      setNotice(
        "Draft exported. It is not approved and nothing was sent to Pro2Pro. Import the file in its review workspace.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid brief");
    }
  }
  return (
    <div className="journey xplore-journey">
      <header className="journey-nav">
        <Link href="/" className="journey-brand">
          xplore<span>more</span>
          <small> / evidence workbench</small>
        </Link>
        <nav aria-label="Workbench navigation">
          <Link href="/problems">All problems</Link>
          <a href="https://protopro.vercel.app/workspace">Pro2Pro review ↗</a>
          <a href="https://github.com/dilipna/xplore_more">Source ↗</a>
        </nav>
      </header>
      <main>
        <section className="journey-intro">
          <p className="journey-kicker">CONNECTED WORKFLOW / 01</p>
          <h1>
            A signal to inspect.
            <br />
            <em>A problem to define.</em>
          </h1>
          <p>
            Start with the original report. Define who needs help, what a small
            prototype should do, and the behavior a reviewer can actually test.
          </p>
          <div
            className="journey-steps"
            aria-label="Evidence to product stages"
          >
            <span className="active">
              01 <b>XploreMore evidence</b>
            </span>
            <span>
              02 <b>Human scope review</b>
            </span>
            <span>
              03 <b>Pro2Pro build</b>
            </span>
            <span>
              04 <b>Tests & acceptance</b>
            </span>
          </div>
        </section>
        <div className="journey-toolbar">
          <div>
            <p className="journey-kicker">PROBLEM → SPECIFICATION</p>
            <h2>Carry the source into the build.</h2>
          </div>
          <div className="journey-buttons">
            <button
              onClick={() => {
                setBrief(parseBrief(JSON.stringify(example)));
                setError("");
                setNotice(
                  "Historical example loaded with a sample specification. No live data was requested.",
                );
              }}
            >
              Load recorded example
            </button>
            <Link href="/problems">Choose a live problem →</Link>
          </div>
        </div>
        <p className="journey-note">
          Recorded examples come from committed September 2026 source snapshots.
          For a current record, open a problem and choose “Draft a product
          brief.” Counts are reporting signals, not market validation.
        </p>
        {error && (
          <p role="alert" className="journey-error">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="journey-notice">
            {notice}
          </p>
        )}
        {!brief ? (
          <div className="journey-empty">
            <span>FIRST, UNDERSTAND THE EVIDENCE</span>
            <h2>
              What was reported?
              <br />
              What is still an assumption?
            </h2>
            <p>
              Inspect the source before choosing a solution. The workbench keeps
              the evidence next to the specification, so the connection stays
              reviewable.
            </p>
            <div className="journey-orbit" aria-hidden="true">
              <i />
              <i />
              <b>
                PROBLEM
                <br />
                EVIDENCE
              </b>
            </div>
          </div>
        ) : (
          <div className="journey-grid">
            <section className="journey-panel">
              <p className="journey-kicker">01 / EVIDENCE SNAPSHOT</p>
              <h2>{brief.source.statement}</h2>
              <div className="journey-metrics">
                <span>
                  <b>{brief.source.voice_count}</b> reported voice(s)
                </span>
                <span>
                  <b>{brief.source.source_count}</b> source(s)
                </span>
                <span>
                  <b>#{brief.source.problem_id}</b> problem identity
                </span>
              </div>
              <p className="journey-note">
                Captured {brief.source.captured_at}
              </p>
              {brief.source.evidence.map((e, i) => (
                <article className="journey-evidence" key={i}>
                  <span>E{i + 1} / ORIGINAL REPORT</span>
                  <blockquote>{e.excerpt}</blockquote>
                  <a href={e.url} target="_blank" rel="noreferrer">
                    Inspect original source ↗
                  </a>
                </article>
              ))}
              <p className="journey-note">{brief.source.limitations}</p>
              <div className="journey-evidence">
                <span>BEFORE YOU BUILD</span>
                <h3>Separate the report from the proposed remedy.</h3>
                <p className="journey-note">
                  A request for approval support does not establish that this
                  prototype is the right solution. Review the source, existing
                  alternatives and the intended user. Record assumptions in the
                  scope.
                </p>
              </div>
            </section>
            <section className="journey-panel">
              <p className="journey-kicker">02 / BOUNDED PRODUCT BRIEF</p>
              <h2>Write a testable specification.</h2>
              <label htmlFor="target-user">Who needs help?</label>
              <input
                id="target-user"
                maxLength={1000}
                value={brief.spec.target_user}
                onChange={(e) => patchSpec("target_user", e.target.value)}
              />
              <label htmlFor="goal">
                What should this prototype accomplish?
              </label>
              <textarea
                id="goal"
                maxLength={1000}
                rows={2}
                value={brief.spec.goal}
                onChange={(e) => patchSpec("goal", e.target.value)}
              />
              <label htmlFor="included">
                In scope · one item per line, up to six
              </label>
              <textarea
                id="included"
                rows={3}
                value={brief.spec.in_scope.join("\n")}
                onChange={(e) => patchList("in_scope", e.target.value)}
              />
              <label htmlFor="excluded">
                Out of scope · one item per line, up to six
              </label>
              <textarea
                id="excluded"
                rows={3}
                value={brief.spec.out_of_scope.join("\n")}
                onChange={(e) => patchList("out_of_scope", e.target.value)}
              />
              <h3>Acceptance criteria</h3>
              <p className="journey-note">
                Use observable behavior. The first version targets a
                browser-only tool with no backend or external API dependency.
              </p>
              {brief.spec.acceptance.map((c, i) => (
                <fieldset className="journey-criterion-editor" key={i}>
                  <legend>Check {i + 1}</legend>
                  {(["given", "when", "then"] as const).map((field) => (
                    <label key={field}>
                      {field[0].toUpperCase() + field.slice(1)}
                      <input
                        maxLength={1000}
                        aria-label={`Check ${i + 1} ${field}`}
                        value={c[field]}
                        onChange={(e) =>
                          patchCriterion(i, field, e.target.value)
                        }
                      />
                    </label>
                  ))}
                </fieldset>
              ))}
              <button
                disabled={brief.spec.acceptance.length >= 6}
                onClick={() =>
                  setBrief({
                    ...brief,
                    spec: {
                      ...brief.spec,
                      acceptance: [
                        ...brief.spec.acceptance,
                        { given: "", when: "", then: "" },
                      ],
                    },
                  })
                }
              >
                Add acceptance criterion
              </button>
              <div className="journey-buttons" style={{ marginTop: 24 }}>
                <button onClick={exportDraft}>Validate & export draft ↓</button>
                <a href="https://protopro.vercel.app/workspace">
                  Open Pro2Pro review →
                </a>
              </div>
              <p className="journey-note">
                Export creates a local JSON file. A human must approve the exact
                imported snapshot in Pro2Pro before execution. No model runs on
                this page.
              </p>
            </section>
          </div>
        )}
        <section className="journey-boundaries">
          <h2>One evidence trail. Distinct responsibilities.</h2>
          <div>
            <article>
              <span>XPLOREMORE</span>
              <h3>Find and inspect the signal.</h3>
              <p>
                Classify and cluster public reports with explainable ranking.
                Preserve original links and the known limitations of
                machine-made labels.
              </p>
            </article>
            <article>
              <span>HUMAN REVIEW</span>
              <h3>Choose what deserves a build.</h3>
              <p>
                Decide whether the problem matters, challenge assumptions, and
                approve a precise scope. A high demand score cannot make that
                decision for you.
              </p>
            </article>
            <article>
              <span>PRO2PRO</span>
              <h3>Build against an approved brief.</h3>
              <p>
                Carry the snapshot into the build. Validate the actual result
                separately before accepting or publishing it.
              </p>
            </article>
          </div>
        </section>
      </main>
      <footer className="journey-footer">
        <span>Built by Dilip Nallamasa · XploreMore × Pro2Pro</span>
        <a href="https://github.com/dilipna/xplore_more/blob/main/docs/evidence-to-product.md">
          Methods & handoff contract ↗
        </a>
      </footer>
    </div>
  );
}

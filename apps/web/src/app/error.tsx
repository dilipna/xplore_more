"use client";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto max-w-xl px-5 py-24 text-center">
      <p className="font-mono text-sm text-amber-400">something went wrong</p>
      <h1 className="mt-3 text-2xl font-semibold">This page failed to render.</h1>
      <p className="mt-3 text-fg-400">The rest of the site still works. Try again in a moment.</p>
      <button
        onClick={reset}
        className="mt-8 rounded-xl bg-signal-400 px-5 py-2.5 text-sm font-semibold text-field-950"
      >
        Retry
      </button>
    </div>
  );
}

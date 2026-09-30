"use client";

export function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="rounded-full border border-field-600 px-4 py-1.5 text-sm font-semibold text-fg-200 hover:border-signal-400 hover:text-signal-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-400 print:hidden"
    >
      Print
    </button>
  );
}

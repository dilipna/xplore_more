import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-5 py-24 text-center">
      <p className="font-mono text-sm text-signal-400">404</p>
      <h1 className="mt-3 text-2xl font-semibold">Nothing here.</h1>
      <p className="mt-3 text-fg-400">That problem or story doesn&apos;t exist, or has aged out of the 30-day window.</p>
      <Link href="/" className="mt-8 inline-block rounded-xl bg-signal-400 px-5 py-2.5 text-sm font-semibold text-field-950">
        Back to problems
      </Link>
    </div>
  );
}

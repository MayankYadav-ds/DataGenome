"use client";
import Link from "next/link";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="public-wrap">
      <h1>This view could not load</h1>
      <p>No dataset changes were requested by this error page.</p>
      <button onClick={reset}>Try again</button>
      <Link href="/app">Return to workspace</Link>
    </main>
  );
}

import Link from "next/link";

// Branded 404 so a bad URL never shows Next's default unstyled screen.
export default function NotFound() {
  return <main className="route-error">
    <p className="eyebrow">Error 404</p>
    <h1>We couldn’t find <em>that page.</em></h1>
    <p className="route-error-copy">The link may be out of date, or the page may have moved. Let’s get you back on track.</p>
    <div className="route-error-actions">
      <Link className="button button-primary" href="/">Back to home <span>→</span></Link>
      <Link className="button button-secondary" href="/dashboard">Open dashboard</Link>
    </div>
  </main>;
}

import Link from "next/link";

const pillars = [
  ["01", "A clearer front door", "Launch a polished clinic website with guided choices and no broken layouts."],
  ["02", "A steadier day", "Keep requests, appointments, queue, and follow-ups in one focused workspace."],
  ["03", "A safer foundation", "Tenant-aware permissions and auditability are part of the product from day one."],
];

export default function HomePage() {
  return <main>
    <nav className="nav shell" aria-label="Primary navigation"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="nav-links"><a href="#why">Why carefully</a><a href="#principles">Principles</a><Link className="nav-cta" href="/login">Sign in <span>↗</span></Link></div></nav>
    <section className="hero shell" aria-labelledby="hero-title"><div className="hero-copy"><p className="eyebrow"><span className="eyebrow-dot" /> Clinic operations, with room to breathe</p><h1 id="hero-title">Make care feel <em>well run.</em></h1><p className="hero-lede">A thoughtful digital home for independent doctors and small clinics — from first impression to finished follow-up.</p><div className="hero-actions"><Link className="button button-primary" href="/login">Enter the workspace <span>→</span></Link><a className="text-link" href="#why">See how it works <span>↓</span></a></div></div><div className="hero-art" aria-label="Illustration of a clinic day" role="img"><div className="sun"/><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="art-card card-main"><span className="card-kicker">TODAY / CLINIC TIME</span><strong>Good morning,<br />care team.</strong><div className="mini-rule"/><span className="card-note">Appointments · follow-ups</span></div><div className="art-card card-float"><span className="pulse"/><span>Next up</span><strong>Appointment</strong><small>Consultation · ready</small></div><span className="scribble scribble-a">a calmer day</span><span className="scribble scribble-b">✳</span></div></section>
    <section className="principles shell" id="why" aria-labelledby="why-title"><div className="section-intro"><p className="eyebrow">THE POINT OF IT</p><h2 id="why-title">The small things<br /><em>add up.</em></h2></div><div className="pillar-grid">{pillars.map(([number, title, text]) => <article className="pillar" key={number}><span className="pillar-number">{number}</span><h3>{title}</h3><p>{text}</p></article>)}</div></section>
    <section className="quote-band" id="principles"><div className="shell quote-inner"><p>“The best technology is the kind that gives you your attention back.”</p><span>— the idea behind carefully</span></div></section>
    <footer className="footer shell"><span className="wordmark">care<span>/</span>fully</span><span>Phase 1 foundation · built for better clinic days</span></footer>
  </main>;
}

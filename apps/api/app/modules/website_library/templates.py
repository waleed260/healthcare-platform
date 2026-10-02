"""Code-defined website template library: specialty full-site templates and reusable page templates (blueprint §19.3)."""
from __future__ import annotations

from typing import Any

LEGAL_PAGES = (
    ("privacy", "Privacy policy", "How we collect, use and protect your personal and health information."),
    ("cancellation", "Cancellation policy", "Please give us at least 24 hours' notice to cancel or reschedule an appointment."),
    ("medical-disclaimer", "Medical disclaimer", "Website content is for general information and is not medical advice."),
)


def section(kind: str, heading: str, body: str = "", *, eyebrow: str = "", layout: str = "text", button: tuple[str, str] | None = None, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    content: dict[str, Any] = {"heading": heading, "body": body, "eyebrow": eyebrow, "items": items or []}
    if button:
        content["button_label"], content["button_href"] = button
    return {"section_type": kind, "layout_key": layout, "content": content}


BOOK = ("Book appointment", "/book")


def _legal_pages() -> list[dict[str, Any]]:
    return [{"slug": slug, "title": title, "seo_title": title, "sections": [section("legal", title, body)]} for slug, title, body in LEGAL_PAGES]


def _site(key: str, name: str, specialty: str, description: str, base: str, colors: dict[str, str], headline: str, sub: str, service_items: list[str], faq: list[tuple[str, str]], fonts: tuple[str, str] = ("serif", "sans")) -> dict[str, Any]:
    return {
        "key": key, "name": name, "specialty": specialty, "description": description, "template_key": base,
        "theme": {"colors": colors, "typography": {"heading_font": fonts[0], "body_font": fonts[1]}, "buttons": {"style": "solid", "radius": 6}},
        "header": {"nav": [{"label": "Services", "href": "/#services"}, {"label": "Doctors", "href": "/#doctors"}, {"label": "Results", "href": "/#results"}, {"label": "FAQ", "href": "/#faq"}, {"label": "Contact", "href": "/#contact"}], "sticky": True, "show_book_cta": True},
        "footer": {"columns": [{"kind": "about", "title": name}, {"kind": "services", "title": "Services"}, {"kind": "hours", "title": "Hours"}, {"kind": "contact", "title": "Contact"}, {"kind": "legal", "title": "Legal"}], "show_legal_links": True},
        "pages": [
            {"slug": "home", "title": "Home", "seo_title": f"{name} | Book online", "sections": [
                section("hero", headline, sub, eyebrow=specialty.title(), layout="split", button=BOOK),
                section("services", "Our services", "Everything we offer, with clear pricing and durations.", layout="cards", items=[{"title": item} for item in service_items]),
                section("doctor_profile", "Meet your doctors", "Experienced clinicians who explain every step.", layout="grid"),
                section("results", "Real results", "Approved before/after cases shared with patient consent.", layout="slider"),
                section("testimonials", "What patients say", "", layout="cards"),
                section("faq", "Questions, answered", "", layout="accordion", items=[{"question": q, "answer": a} for q, a in faq]),
                section("appointment_cta", "Ready when you are", "Choose a time that suits you.", layout="banner", button=BOOK),
                section("hours", "Opening hours", ""), section("location", "Find us", "", layout="map"), section("contact", "Talk to us", "We reply within one working day."),
            ]},
            {"slug": "about", "title": "About", "seo_title": f"About {name}", "sections": [section("about", f"About {name}", "Our story, our team and how we care for patients.")]},
            *_legal_pages(),
        ],
    }


SITE_TEMPLATES: list[dict[str, Any]] = [
    _site("dental_bright", "Dental Bright", "dental", "Clean, reassuring site for dental practices with implants, whitening and check-ups.", "calm_clinic", {"primary": "#0f5f73", "accent": "#2fa8a0", "background": "#f6fbfb", "text": "#12333d"}, "Healthy smiles, gentle care", "Check-ups, implants, whitening and emergency dentistry in one friendly clinic.", ["Check-up & cleaning", "Teeth whitening", "Dental implants", "Root canal", "Braces & aligners"], [("Does treatment hurt?", "We use modern anaesthesia and gentle techniques."), ("Can I pay in instalments?", "Ask the front desk about treatment plans.")]),
    _site("hair_restore", "Hair Restore", "hair", "Confident, editorial site for hair transplant and restoration clinics.", "editorial_practice", {"primary": "#2b2d42", "accent": "#c8553d", "background": "#faf8f5", "text": "#1d1e2c"}, "Natural hair, naturally yours", "Assessment-led hair transplant and restoration with transparent graft planning.", ["Hair transplant (FUE)", "PRP therapy", "Beard transplant", "Hair-loss consultation"], [("How many grafts will I need?", "Your Norwood stage and donor assessment decide this at consultation."), ("When will I see results?", "Most patients see full results at 9–12 months.")], ("serif", "sans")),
    _site("skin_glow", "Skin Glow", "skin", "Warm, tactile site for skin and aesthetics studios with packages.", "warm_studio", {"primary": "#8a4f5d", "accent": "#e0a458", "background": "#fdf7f4", "text": "#3b2428"}, "Skin that feels like you", "Facials, laser and injectables with personalised session packages.", ["HydraFacial", "Laser hair removal", "Chemical peel", "Skin boosters", "Session packages"], [("Are packages refundable?", "Unused sessions can be transferred within the validity period."), ("Is there downtime?", "Most treatments have little to none.")], ("serif", "humanist")),
    _site("derma_care", "Derma Care", "dermatology", "Clinical, trustworthy site for dermatology practices.", "calm_clinic", {"primary": "#1f4e79", "accent": "#5aa469", "background": "#f7f9fb", "text": "#17283a"}, "Expert care for your skin", "Diagnosis, prescriptions and follow-up for acne, eczema, pigmentation and more.", ["Skin consultation", "Acne treatment", "Eczema & psoriasis", "Mole check", "Pigmentation"], [("Do I need a referral?", "No, you can book directly."), ("Will I get a prescription?", "If clinically appropriate, yes.")], ("sans", "sans")),
    _site("general_clinic", "General Clinic", "general", "A neutral starting point for any clinic or future specialty.", "calm_clinic", {"primary": "#274c42", "accent": "#e77b5c", "background": "#f5f4ee", "text": "#1c2928"}, "Care that fits your life", "Book online, see the right clinician, and stay on top of your follow-ups.", ["General consultation", "Health check", "Follow-up visit"], [("How do I book?", "Use the Book appointment button.")]),
]

PAGE_TEMPLATES: list[dict[str, Any]] = [
    {"key": "service_page", "name": "Service page", "description": "Overview, benefits, pricing and a booking call to action.", "sections": [section("hero", "Service name", "Short description of the treatment.", layout="split", button=BOOK), section("about", "What to expect", "Describe the procedure, duration and aftercare."), section("pricing", "Pricing", "", layout="cards"), section("faq", "Common questions", "", layout="accordion"), section("appointment_cta", "Book this treatment", "", layout="banner", button=BOOK)]},
    {"key": "doctor_page", "name": "Doctor page", "description": "Profile, credentials, services and availability.", "sections": [section("doctor_profile", "Doctor name", "Credentials, experience and approach.", layout="profile"), section("services", "Services offered", "", layout="cards"), section("appointment_cta", "Book with this doctor", "", layout="banner", button=BOOK)]},
    {"key": "location_page", "name": "Location page", "description": "Address, map, hours and local team.", "sections": [section("location", "Branch name", "", layout="map"), section("hours", "Opening hours", ""), section("contact", "Contact this branch", ""), section("appointment_cta", "Book at this branch", "", layout="banner", button=BOOK)]},
    {"key": "landing_page", "name": "Campaign landing page", "description": "Focused page for ads: offer, proof and a lead form.", "sections": [section("hero", "Limited-time offer", "One clear promise.", layout="split", button=BOOK), section("results", "Proof", "", layout="slider"), section("testimonials", "Reviews", "", layout="cards"), section("lead_form", "Get a callback", "Leave your details and we will call you.")]},
    {"key": "blog_page", "name": "Article / blog post", "description": "A long-form article with a booking prompt.", "sections": [section("about", "Article title", "Write your article here."), section("appointment_cta", "Questions? Talk to us", "", layout="banner", button=BOOK)]},
    {"key": "before_after_page", "name": "Before & after", "description": "Approved case gallery.", "sections": [section("results", "Before & after", "Only patient media approved for website use appears here.", layout="gallery"), section("appointment_cta", "Start your journey", "", layout="banner", button=BOOK)]},
]

SECTION_PRESETS: dict[str, list[str]] = {
    "hero": ["split", "image", "video", "doctor", "booking"], "services": ["cards", "grid", "slider", "featured", "pricing"],
    "doctor_profile": ["grid", "featured", "carousel", "team"], "results": ["slider", "gallery", "cases"],
    "testimonials": ["cards", "reviews", "statistics", "logos"], "appointment_cta": ["banner", "call", "lead", "consultation"],
    "about": ["text", "image_text", "video", "timeline", "comparison"], "location": ["map", "text"], "faq": ["accordion", "list"],
}

SITE_BY_KEY = {template["key"]: template for template in SITE_TEMPLATES}
PAGE_BY_KEY = {template["key"]: template for template in PAGE_TEMPLATES}

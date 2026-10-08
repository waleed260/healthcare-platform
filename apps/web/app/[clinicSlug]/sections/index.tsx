import type { SectionProps } from "./types";
import { text, items } from "./types";
import FormEmbed from "../form-embed";
import HeroSection from "./hero";
import ServicesSection from "./services";
import DoctorsSection from "./doctors";
import ContactSection from "./contact";
import ResultsSection from "./results";
import SocialProofSection from "./social-proof";
import FaqSection from "./faq";
import TimelineSection from "./timeline";
import GallerySection from "./gallery";
import VideoSection from "./video";
import ComparisonSection from "./comparison";
import FallbackSection from "./fallback";

export type { SectionProps } from "./types";
export type { Content, Section, Branch, PublicCatalog, ResultMedia, TemplateKey } from "./types";
export { text, items, label } from "./types";

export default function SectionBlock(props: SectionProps) {
  const type = props.section.section_type.toLowerCase();
  const records = items(props.section.content ?? {});

  if (type === "lead_form") {
    const formId = text(records[0]?.form_id);
    if (formId) return <FormEmbed clinicSlug={props.clinicSlug} formId={formId} brand={props.brand} heading={text(props.section.content?.heading)} />;
  }
  if (["hero", "banner"].includes(type)) return <HeroSection {...props} />;
  if (["services", "service"].includes(type) || (records.length > 0 && type.includes("service"))) return <ServicesSection {...props} />;
  if (["doctors", "doctor", "team", "care_team"].includes(type)) return <DoctorsSection {...props} />;
  if (["hours", "location", "contact"].includes(type)) return <ContactSection {...props} />;
  if (type === "results") return <ResultsSection {...props} />;
  if (["testimonials", "pricing", "statistics"].includes(type)) return <SocialProofSection {...props} />;
  if (type === "faq") return <FaqSection {...props} />;
  if (type === "timeline" || type === "process" || type === "steps") return <TimelineSection {...props} />;
  if (type === "gallery" || type === "masonry") return <GallerySection {...props} />;
  if (type === "video") return <VideoSection {...props} />;
  if (type === "comparison" || type === "comparison_table") return <ComparisonSection {...props} />;
  return <FallbackSection {...props} />;
}

import type { Metadata } from "next";
import RoadmapView from "./roadmap-view";

export const metadata: Metadata = {
  title: "care/fully CRM — Workflow Roadmap",
  description:
    "A visual roadmap of the care/fully clinic CRM, showing how its workspaces and everyday clinic workflows connect.",
  openGraph: {
    title: "care/fully CRM — Workflow Roadmap",
    description:
      "Explore how leads, appointments, patients, clinical care, billing, inventory and clinic management connect.",
    type: "website",
  },
};

export default function RoadmapPage() {
  return <RoadmapView />;
}

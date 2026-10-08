import type { SectionProps } from "./types";
import { text } from "./types";

export default function VideoSection({ section, template }: SectionProps) {
  const content = section.content ?? {};
  const heading = text(content.heading);
  const body = text(content.body);
  const style = `template-${template}`;
  const videoUrl = text(content.video_url ?? content.url);
  const posterUrl = text(content.poster_url ?? content.poster ?? content.image);

  return <section className={`public-section public-video ${style}`} id="video"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "VIDEO")}</p><h2>{heading || "See it in action."}</h2>{body && <p>{body}</p>}</div><div className="public-video-player">{videoUrl ? <video controls preload="none" poster={posterUrl || undefined} style={{ width: "100%", maxWidth: "800px", borderRadius: "8px" }}><source src={videoUrl} /></video> : posterUrl ? <img src={posterUrl} alt={heading || "Video thumbnail"} style={{ width: "100%", maxWidth: "800px", borderRadius: "8px" }} /> : <p>No video configured for this section.</p>}</div></section>;
}

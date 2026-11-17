import { redirect } from "next/navigation";

// Analytics was merged into Reports (its charts live in the Reports "Trends" tab).
// Keep the route as a permanent redirect so existing links and bookmarks don't 404.
export default function AnalyticsPage() {
  redirect("/reports");
}

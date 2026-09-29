import { ReactNode } from "react";
import WorkspaceShell from "./workspace-shell";

export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return <WorkspaceShell>{children}</WorkspaceShell>;
}

import { ReactNode } from "react";
import WorkspaceShell from "./workspace-shell";
import { ToastProvider } from "./_lib/toast";
import { ConfirmProvider } from "./_lib/confirm";

export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return <ToastProvider><ConfirmProvider><WorkspaceShell>{children}</WorkspaceShell></ConfirmProvider></ToastProvider>;
}

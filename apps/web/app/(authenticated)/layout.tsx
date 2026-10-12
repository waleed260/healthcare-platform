import { ReactNode } from "react";
import WorkspaceShell from "./workspace-shell";
import { ToastProvider } from "./_lib/toast";
import { ConfirmProvider } from "./_lib/confirm";
import { ClinicProvider } from "./_lib/clinic-context";

export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return <ToastProvider><ConfirmProvider><ClinicProvider><WorkspaceShell>{children}</WorkspaceShell></ClinicProvider></ConfirmProvider></ToastProvider>;
}

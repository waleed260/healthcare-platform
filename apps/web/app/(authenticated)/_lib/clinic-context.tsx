"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api } from "./client";

type ClinicData = { default_currency: string };

const ClinicContext = createContext<ClinicData>({ default_currency: "PKR" });

export function useClinicCurrency(): string {
  return useContext(ClinicContext).default_currency;
}

export function ClinicProvider({ children }: { children: ReactNode }) {
  const [clinic, setClinic] = useState<ClinicData>({ default_currency: "PKR" });

  useEffect(() => {
    let mounted = true;
    void api<{ default_currency?: string }>("/api/v1/clinic/context")
      .then((data) => { if (mounted && data?.default_currency) setClinic({ default_currency: data.default_currency }); })
      .catch(() => {});
    return () => { mounted = false; };
  }, []);

  return <ClinicContext value={clinic}>{children}</ClinicContext>;
}

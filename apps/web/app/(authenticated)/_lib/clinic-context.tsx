"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { cachedFetch } from "./session-cache";

type ClinicData = { default_currency: string; name: string };

const ClinicContext = createContext<ClinicData>({ default_currency: "PKR", name: "" });

export function useClinicCurrency(): string {
  return useContext(ClinicContext).default_currency;
}

export function useClinicName(): string {
  return useContext(ClinicContext).name;
}

export function ClinicProvider({ children }: { children: ReactNode }) {
  const [clinic, setClinic] = useState<ClinicData>({ default_currency: "PKR", name: "" });

  useEffect(() => {
    let mounted = true;
    void cachedFetch<{ default_currency?: string; name?: string }>("/api/v1/clinic/context", 60_000)
      .then((data) => {
        if (!mounted || !data) return;
        setClinic((c) => ({ default_currency: data.default_currency ?? c.default_currency, name: data.name ?? c.name }));
      })
      .catch(() => {});
    return () => { mounted = false; };
  }, []);

  return <ClinicContext value={clinic}>{children}</ClinicContext>;
}

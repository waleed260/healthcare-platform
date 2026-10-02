"use client";

import { useEffect, useState } from "react";
import { api } from "../_lib/client";

type Doctor = { id: string; public_name: string };

// eslint-disable-next-line no-unused-vars
type Change = (providerId: string) => void;

/** Optional provider attribution for an invoice line (drives provider revenue and commission reports). */
export default function ProviderSelect({ value, onChange }: { value: string; onChange: Change }) {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  useEffect(() => {
    void api<Doctor[]>("/api/v1/doctors?limit=100").then((rows) => setDoctors(Array.isArray(rows) ? rows : [])).catch(() => setDoctors([]));
  }, []);
  if (doctors.length === 0) return null;
  return <label>Provider <span className="field-optional">optional</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">Not attributed</option>{doctors.map((doctor) => <option key={doctor.id} value={doctor.id}>{doctor.public_name}</option>)}</select></label>;
}

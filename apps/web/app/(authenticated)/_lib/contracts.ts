// Shared entity types consumed by the frontend.
// Keep in sync with the API response shapes; the generator
// (generate_types.py) handles enum literals from the OpenAPI spec.

export type PatientSummary = {
  id: string;
  patient_number: string;
  full_name: string;
  normalized_email: string | null;
  normalized_phone: string | null;
  status: string;
  version: number;
};

export type PatientDetail = PatientSummary & {
  date_of_birth: string | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  emergency_contact_relation: string | null;
  preferred_communication: string | null;
  contraindications: string | null;
  allergies_summary: string | null;
};

export type PatientRef = Pick<PatientSummary, "id" | "full_name" | "patient_number">;

export type SessionInfo = {
  user_id?: string;
  clinic_id?: string | null;
  clinic_slug?: string | null;
  display_name?: string;
  email?: string;
  is_platform_admin?: boolean;
  permissions?: string[];
};

export type InvoiceSummary = {
  id: string;
  patient_id: string;
  invoice_number: string;
  currency: string;
  subtotal_minor: number;
  discount_minor: number;
  tax_minor: number;
  total_minor: number;
  paid_minor: number;
  status: string;
  issued_at: string;
  notes: string | null;
  version: number;
};

export type InvoiceRef = Pick<InvoiceSummary, "id" | "invoice_number" | "total_minor" | "paid_minor" | "status" | "issued_at" | "currency">;

export type DoctorRef = {
  id: string;
  public_name: string;
  specialty?: string | null;
};

export type ServiceRef = {
  id: string;
  name: string;
  duration_minutes: number;
  amount_minor?: number | null;
  currency?: string | null;
};

export type BranchRef = {
  id: string;
  code: string;
  name: string;
};

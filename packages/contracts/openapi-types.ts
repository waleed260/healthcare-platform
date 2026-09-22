// GENERATED FILE. Do not edit; run: python3 packages/contracts/generate_types.py

export type AnnouncementCreateSeverityValue = "info" | "warning" | "critical";
export type AppointmentTransitionRequestToStatusValue = "confirmed" | "cancelled" | "arrived" | "waiting" | "in_consultation" | "completed" | "no_show";
export type CatalogStatusUpdateStatusValue = "active" | "archived";
export type ClinicStatusUpdateStatusValue = "active" | "suspended" | "archived";
export type ConsentCreateStatusValue = "granted" | "withdrawn" | "declined";
export type ExportJobCreateExportTypeValue = "patient_access" | "audit";
export type FollowUpCreatePriorityValue = "low" | "normal" | "high";
export type PatientNoteCreateVisibilityValue = "clinic" | "care_team" | "private_doctor";
export type PrivacyRequestCreateRequestTypeValue = "access" | "correction" | "deletion" | "restriction";
export type PrivacyRequestResolveExpectedStatusValue = "requested" | "in_review" | "approved" | "rejected" | "completed";
export type PrivacyRequestResolveStatusValue = "in_review" | "approved" | "rejected" | "completed";
export type StaffStatusUpdateStatusValue = "active" | "suspended" | "deactivated";
export type SubscriptionUpdateStatusValue = "trialing" | "active" | "past_due" | "cancelled";

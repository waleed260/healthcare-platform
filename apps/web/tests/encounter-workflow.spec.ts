import { test, expect } from "./fixtures";

const permissions = [
  "patient.read", "patient.write", "clinical.read", "clinical.manage",
  "appointment.read", "appointment.manage", "queue.read",
];

test.describe("Clinical Encounter Workflow", () => {
  const patient = { id: "p1", full_name: "Sara Ahmed", patient_number: "PT-100", date_of_birth: "1990-05-15", status: "active" };
  const doctor = { id: "d1", public_name: "Dr. Khan", specialty: "General" };
  let encounters: Record<string, unknown>[] = [];
  let encounterVersion = 1;
  let encounterStatus = "draft";

  test.beforeEach(async ({ page }) => {
    encounters = [];
    encounterVersion = 1;
    encounterStatus = "draft";

    await page.route("**/api/v1/**", async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      const method = route.request().method();
      let data: unknown = [];
      let status = 200;

      if (path.endsWith("/auth/me")) {
        data = { user_id: "u1", clinic_id: "c1", display_name: "Staff", permissions, clinic_slug: "demo" };
      } else if (path.endsWith("/notifications")) {
        data = [];
      } else if (path.endsWith("/doctors")) {
        data = [doctor];
      } else if (path.match(/\/patients\/p1$/) && method === "GET") {
        data = { ...patient, allergies_summary: "Penicillin", contraindications: null, emergency_contact_name: "Ali Ahmed", emergency_contact_phone: "+92300111222", emergency_contact_relation: "Spouse" };
      } else if (path.endsWith("/patients") && method === "GET") {
        const search = url.searchParams.get("search");
        data = search ? [patient] : [patient];
      } else if (path.endsWith("/encounters") && method === "GET") {
        data = encounters.map((e) => ({
          ...e, patient_name: patient.full_name, doctor_name: doctor.public_name,
        }));
      } else if (path.endsWith("/encounters") && method === "POST") {
        const body = JSON.parse(await route.request().postData() ?? "{}");
        const enc = {
          id: "enc-1", clinic_id: "c1", patient_id: body.patient_id, patient_name: patient.full_name,
          mrn: patient.patient_number, appointment_id: body.appointment_id ?? null,
          doctor_id: body.doctor_id, doctor_name: doctor.public_name, doctor_specialty: doctor.specialty,
          branch_id: null, branch_name: null, encounter_type: body.encounter_type ?? "general",
          status: "draft", chief_complaint: body.chief_complaint ?? null,
          history_present_illness: null, examination_findings: null, diagnosis: null,
          investigations: null, treatment_plan: null, medications: [], procedures_performed: null,
          follow_up_instructions: null, follow_up_date: null,
          arrival_vitals: null, discharge_vitals: null, discharge_notes: null, internal_notes: null,
          finalized_at: null, finalized_by: null,
          created_at: new Date().toISOString(), updated_at: new Date().toISOString(), version: 1,
          arrival_mode: null, arrival_datetime: null, attendant_name: null, attendant_phone: null,
          condition_on_arrival: null, known_allergies: null, allergy_status: "unknown",
          medical_history: null, current_medications_text: null, symptom_duration: null,
          gcs_eye: null, gcs_verbal: null, gcs_motor: null, pain_score: null,
          investigation_results: null, clinical_assessment: null,
          administered_treatments: [], administered_procedures: [],
          treatment_response: null, adverse_reactions: null,
          discharge_condition: null, discharge_outcome: null, discharge_destination: null,
          discharge_reason: null, discharge_datetime: null, discharged_by: null,
          discharge_instructions: null, warning_signs: null, medicine_guidance: null,
          follow_up_clinician: null, follow_up_department: null, referral_instructions: null,
          amendment_history: [],
          patient_dob: patient.date_of_birth, patient_allergies: "Penicillin",
          patient_contraindications: null, emergency_contact_name: "Ali Ahmed",
          emergency_contact_phone: "+92300111222", emergency_contact_relation: "Spouse",
        };
        encounters.push(enc);
        encounterVersion = 1;
        encounterStatus = "draft";
        data = enc;
        status = 201;
      } else if (path.match(/\/encounters\/enc-1$/) && method === "PATCH") {
        encounterVersion++;
        data = { ...encounters[0], status: encounterStatus, version: encounterVersion, updated_at: new Date().toISOString() };
      } else if (path.match(/\/encounters\/enc-1\/status$/) && method === "POST") {
        const body = JSON.parse(await route.request().postData() ?? "{}");
        encounterStatus = body.status;
        encounterVersion++;
        data = { id: "enc-1", status: encounterStatus, finalized_at: encounterStatus === "finalized" ? new Date().toISOString() : null, finalized_by: null, version: encounterVersion, updated_at: new Date().toISOString() };
      } else if (path.match(/\/encounters\/enc-1\/discharge$/) && method === "POST") {
        encounterStatus = "discharged";
        encounterVersion++;
        data = { ...encounters[0], status: "discharged", version: encounterVersion, discharge_datetime: new Date().toISOString(), updated_at: new Date().toISOString() };
      } else if (path.match(/\/encounters\/enc-1\/amend$/) && method === "POST") {
        encounterVersion++;
        const body = JSON.parse(await route.request().postData() ?? "{}");
        data = { id: "enc-1", status: encounterStatus, amendment_history: [{ field: body.field, old_value: body.old_value, new_value: body.new_value, reason: body.reason, amended_by: "u1", amended_at: new Date().toISOString() }], version: encounterVersion, updated_at: new Date().toISOString() };
      } else if (path.match(/\/encounters\/enc-\d+$/) && method === "GET") {
        const encId = path.split("/").pop();
        const base = encounters.find((e) => (e as { id: string }).id === encId) ?? encounters[0];
        if (base) {
          const st = encId === "enc-1" ? encounterStatus : (base as { status: string }).status;
          const ver = encId === "enc-1" ? encounterVersion : ((base as { version: number }).version ?? 1);
          data = {
            ...base, status: st, version: ver,
            patient_name: patient.full_name, mrn: patient.patient_number,
            doctor_name: doctor.public_name, doctor_specialty: doctor.specialty,
            branch_name: null, patient_dob: patient.date_of_birth,
            patient_allergies: "Penicillin", patient_contraindications: null,
            emergency_contact_name: "Ali Ahmed", emergency_contact_phone: "+92300111222",
            emergency_contact_relation: "Spouse",
            arrival_vitals: null, discharge_vitals: null, medications: [],
            administered_treatments: [], administered_procedures: [],
            amendment_history: [], allergy_status: "unknown",
            finalized_at: st === "finalized" ? new Date().toISOString() : null,
            discharge_datetime: ["discharged", "finalized"].includes(st) ? new Date().toISOString() : null,
          };
        }
      } else if (path.match(/\/encounters\/enc-\d+\/prescriptions$/) && method === "GET") {
        data = [];
      } else if (path.match(/\/encounters\/enc-1\/print$/) && method === "GET") {
        data = { ...encounters[0], status: encounterStatus, version: encounterVersion, clinic_name: "Test Clinic" };
      } else if (path.match(/\/encounters\/enc-1$/) && method === "DELETE") {
        encounters = [];
        data = { id: "enc-1" };
      }

      await route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "r1", next_cursor: null, limit: 100 } }) });
    });
  });

  test("encounters list page loads", async ({ page }) => {
    await page.goto("/encounters");
    await expect(page.locator(".dash-topline")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Encounter forms." })).toBeVisible();
  });

  test("create a new encounter via the form", async ({ page }) => {
    await page.goto("/encounters");
    await page.getByRole("button", { name: /new encounter/i }).click();
    await expect(page.getByText("Start clinical documentation")).toBeVisible();

    // Search and select patient
    await page.getByPlaceholder("Search patient by name").fill("Sara");
    await page.getByText("Sara Ahmed").click();

    // Select doctor
    await page.getByLabel("Doctor").selectOption("d1");

    // Set type
    await page.getByLabel("Type").selectOption("general");

    // Enter chief complaint
    await page.getByPlaceholder("Patient's chief complaint").fill("Fever and headache for 3 days");

    // Submit
    await page.getByRole("button", { name: /create encounter/i }).click();
  });

  test("encounter detail page loads with all tabs", async ({ page }) => {
    // Pre-create an encounter
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "general", status: "draft",
      chief_complaint: "Headache", diagnosis: null, created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(), version: 1, finalized_at: null,
    });

    await page.goto("/encounters/enc-1");
    await expect(page.getByText("Sara Ahmed")).toBeVisible();

    // Check all tabs are present
    const tabs = ["Arrival", "Patient", "Assessment", "Treatment", "Medications", "Vitals", "Discharge", "Prescriptions", "Summary"];
    for (const tabName of tabs) {
      await expect(page.getByRole("tab", { name: tabName }).or(page.locator(".pipeline-tabs button", { hasText: tabName }))).toBeVisible();
    }
  });

  test("navigate through tabs and verify content", async ({ page }) => {
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "general", status: "draft",
      chief_complaint: "Headache", diagnosis: null, created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(), version: 1, finalized_at: null,
    });

    await page.goto("/encounters/enc-1");

    // Patient tab — shows patient info
    await page.locator(".pipeline-tabs button", { hasText: "Patient" }).click();
    await expect(page.getByRole("paragraph").filter({ hasText: "Sara Ahmed" })).toBeVisible();
    await expect(page.getByText("Penicillin")).toBeVisible();

    // Assessment tab — shows chief complaint, GCS, pain score
    await page.locator(".pipeline-tabs button", { hasText: "Assessment" }).click();
    await expect(page.getByText("Chief complaint")).toBeVisible();
    await expect(page.getByText("GLASGOW COMA SCALE")).toBeVisible();
    await expect(page.getByText("Pain score")).toBeVisible();

    // Treatment tab — treatments and procedures sections
    await page.locator(".pipeline-tabs button", { hasText: "Treatment" }).click();
    await expect(page.getByText("No administered treatments")).toBeVisible();
    await expect(page.getByText("No administered procedures")).toBeVisible();

    // Vitals tab — arrival and discharge vitals
    await page.locator(".pipeline-tabs button", { hasText: "Vitals" }).click();
    await expect(page.getByText("ARRIVAL VITALS")).toBeVisible();
    await expect(page.getByText("DISCHARGE VITALS")).toBeVisible();

    // Prescriptions tab
    await page.locator(".pipeline-tabs button", { hasText: "Prescriptions" }).click();
    await expect(page.getByText("No prescriptions")).toBeVisible();
  });

  test("status transitions: draft → in_progress → ready_for_discharge", async ({ page }) => {
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "general", status: "draft",
      chief_complaint: "Headache", diagnosis: null, created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(), version: 1, finalized_at: null,
    });

    await page.goto("/encounters/enc-1");

    // Draft → In Progress
    await expect(page.getByText("Draft")).toBeVisible();
    await page.getByRole("button", { name: "Begin Assessment" }).click();
    await expect(page.getByText("In Progress")).toBeVisible();

    // In Progress → Ready for Discharge
    await page.getByRole("button", { name: "Ready for Discharge" }).click();
  });

  test("discharge workflow requires outcome and confirmation", async ({ page }) => {
    encounterStatus = "ready_for_discharge";
    encounterVersion = 3;
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "general", status: "ready_for_discharge",
      chief_complaint: "Headache", diagnosis: "Tension headache",
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      version: 3, finalized_at: null,
    });

    await page.goto("/encounters/enc-1");

    // Navigate to discharge tab
    await page.locator(".pipeline-tabs button", { hasText: "Discharge" }).click();

    // The discharge button should be visible
    await expect(page.getByRole("button", { name: "Complete Discharge" })).toBeVisible();

    // Select outcome
    await page.getByLabel("Discharge outcome").selectOption("home");

    // Fill discharge condition
    await page.getByPlaceholder("Patient condition at discharge").fill("Stable, afebrile");
  });

  test("summary tab shows encounter data and print button", async ({ page }) => {
    encounterStatus = "discharged";
    encounterVersion = 4;
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "general", status: "discharged",
      chief_complaint: "Headache", diagnosis: "Tension headache",
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      version: 4, finalized_at: null,
    });

    await page.goto("/encounters/enc-1");

    // Go to summary tab
    await page.locator(".pipeline-tabs button", { hasText: "Summary" }).click();
    await expect(page.getByRole("heading", { name: "Encounter Summary" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Print" })).toBeVisible();

    // Amendment form should appear for discharged encounter
    await expect(page.getByText("Amend Record")).toBeVisible();
  });

  test("amendment form visible for discharged encounters", async ({ page }) => {
    encounterStatus = "discharged";
    encounterVersion = 4;
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "general", status: "discharged",
      chief_complaint: "Headache", diagnosis: "Tension headache",
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      version: 4, finalized_at: null,
    });

    await page.goto("/encounters/enc-1");
    await page.locator(".pipeline-tabs button", { hasText: "Summary" }).click();

    // Select field to amend
    await page.getByLabel("Field to amend").selectOption("diagnosis");
    await expect(page.getByText("CURRENT VALUE")).toBeVisible();

    // Fill amendment
    await page.getByLabel("New value").fill("Migraine with aura");
    await page.getByPlaceholder("Required: explain why").fill("Updated after imaging results");

    // Submit button should be enabled
    await expect(page.getByRole("button", { name: "Submit Amendment" })).toBeEnabled();
  });

  test("finalized encounter is read-only", async ({ page }) => {
    encounterStatus = "finalized";
    encounterVersion = 5;
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "general", status: "finalized",
      chief_complaint: "Headache", diagnosis: "Migraine",
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      version: 5, finalized_at: new Date().toISOString(),
    });

    await page.goto("/encounters/enc-1");
    await expect(page.getByText("Finalized", { exact: true })).toBeVisible();

    // Assessment tab should be read-only
    await page.locator(".pipeline-tabs button", { hasText: "Assessment" }).click();
    const textarea = page.locator("textarea").first();
    await expect(textarea).toBeDisabled();

    // No save button should be visible
    await expect(page.getByRole("button", { name: "Save encounter" })).toHaveCount(0);
  });

  test("GCS calculator shows classification", async ({ page }) => {
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "emergency", status: "in_progress",
      chief_complaint: "Head injury", diagnosis: null,
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      version: 1, finalized_at: null,
    });
    encounterStatus = "in_progress";

    await page.goto("/encounters/enc-1");
    await page.locator(".pipeline-tabs button", { hasText: "Assessment" }).click();

    // Set GCS values
    await page.getByLabel("Eye Response (E)").selectOption("4");
    await page.getByLabel("Verbal Response (V)").selectOption("5");
    await page.getByLabel("Motor Response (M)").selectOption("6");

    // Total = 15, should show "Mild"
    await expect(page.getByText("15")).toBeVisible();
    await expect(page.getByText("Mild")).toBeVisible();
  });

  test("status filter tabs work on list page", async ({ page }) => {
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "general", status: "draft",
      chief_complaint: "Headache", diagnosis: null,
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      version: 1, finalized_at: null,
    });

    await page.goto("/encounters");
    await expect(page.getByText("Sara Ahmed")).toBeVisible();

    // Filter tabs should be present
    await expect(page.locator(".pipeline-tabs button", { hasText: "All" })).toBeVisible();
    await expect(page.locator(".pipeline-tabs button", { hasText: "Draft" })).toBeVisible();
    await expect(page.locator(".pipeline-tabs button", { hasText: "In Progress" })).toBeVisible();
    await expect(page.locator(".pipeline-tabs button", { hasText: "Discharged" })).toBeVisible();
    await expect(page.locator(".pipeline-tabs button", { hasText: "Finalized" })).toBeVisible();
  });

  test("delete button present for draft encounters", async ({ page }) => {
    encounters.push({
      id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
      doctor_id: "d1", encounter_type: "general", status: "draft",
      chief_complaint: "Headache", diagnosis: null,
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      version: 1, finalized_at: null,
    });

    await page.goto("/encounters");
    await expect(page.getByText("Delete")).toBeVisible();
  });

  test("edit link present for non-finalized, view link for finalized", async ({ page }) => {
    encounters.push(
      {
        id: "enc-1", clinic_id: "c1", patient_id: "p1", appointment_id: null,
        doctor_id: "d1", encounter_type: "general", status: "draft",
        chief_complaint: "Draft encounter", diagnosis: null,
        created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        version: 1, finalized_at: null,
      },
      {
        id: "enc-2", clinic_id: "c1", patient_id: "p1", appointment_id: null,
        doctor_id: "d1", encounter_type: "general", status: "finalized",
        chief_complaint: "Finalized encounter", diagnosis: "Migraine",
        created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        version: 5, finalized_at: new Date().toISOString(),
      },
    );

    await page.goto("/encounters");
    await expect(page.getByRole("link", { name: "Edit" })).toBeVisible();
    await expect(page.getByRole("link", { name: "View", exact: true })).toBeVisible();
  });
});

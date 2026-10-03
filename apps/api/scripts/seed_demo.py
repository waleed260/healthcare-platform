"""Seed two deliberately synthetic clinics for local demos and browser tests.

This script is intentionally dev-only. It uses the migration/admin connection
so inserts are performed before the runtime-role RLS verification step; the
application itself must still be verified through the runtime role.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid5

import psycopg
from psycopg.rows import dict_row

from app.core.security import hash_password


NAMESPACE = UUID("a59c4f7e-97c1-4c14-9a2e-0f30f5c63d8b")
PASSWORD = os.environ.get("SEED_PASSWORD", "Synthetic-Demo-Only-2026!")


def ident(label: str) -> UUID:
    return uuid5(NAMESPACE, label)


def connection_url() -> str:
    value = os.environ.get("SEED_DATABASE_URL") or os.environ.get("DATABASE_MIGRATION_URL") or os.environ.get("DATABASE_URL")
    if not value:
        raise SystemExit("SEED_DATABASE_URL or DATABASE_URL is required")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    app_env = os.environ.get("APP_ENV", "").lower()
    if app_env not in {"local", "test"}:
        raise SystemExit("Refusing to seed: APP_ENV must be local or test")

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with psycopg.connect(connection_url(), row_factory=dict_row) as db:
        with db.cursor() as cur:
            roles = {row["name"]: row["id"] for row in cur.execute("SELECT id, name FROM roles WHERE clinic_id IS NULL AND is_system = true").fetchall()}
            required_roles = {"owner", "manager", "doctor", "receptionist", "website_editor"}
            if required_roles - roles.keys():
                raise SystemExit("Database is missing system roles; run alembic upgrade head first")

            for clinic_number in ("a", "b"):
                clinic_id = ident(f"clinic-{clinic_number}")
                branch_id = ident(f"branch-{clinic_number}")
                service_id = ident(f"service-{clinic_number}")
                doctor_id = ident(f"doctor-profile-{clinic_number}")
                slug = f"demo-collision-{clinic_number}"
                cur.execute("""
                    INSERT INTO clinics (id, name, slug, timezone, locale, status)
                    VALUES (%s, 'Vale Clinic', %s, 'UTC', 'en', 'active')
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = 'active', archived_at = NULL
                """, (clinic_id, slug))
                cur.execute("""
                    INSERT INTO branches (id, clinic_id, code, name, timezone, address, status)
                    VALUES (%s, %s, 'MAIN', 'Main clinic', 'UTC', '{"city":"Synthetic City"}', 'active')
                    ON CONFLICT (id) DO UPDATE SET status = 'active', archived_at = NULL
                """, (branch_id, clinic_id))
                cur.execute("""
                    INSERT INTO services (id, clinic_id, name, category, short_description, duration_minutes, approval_mode, visibility, status)
                    VALUES (%s, %s, 'General consultation', 'Primary care', 'A synthetic consultation service.', 30, 'staff_approval', 'public', 'active')
                    ON CONFLICT (id) DO UPDATE SET status = 'active', archived_at = NULL
                """, (service_id, clinic_id))
                cur.execute("""
                    INSERT INTO branch_services (clinic_id, branch_id, service_id) VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (clinic_id, branch_id, service_id))

                user_ids: dict[str, UUID] = {}
                for role_name in sorted(required_roles):
                    user_id = ident(f"user-{clinic_number}-{role_name}")
                    user_ids[role_name] = user_id
                    email = f"{role_name}.{clinic_number}@synthetic.example.test"
                    cur.execute("""
                        INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status)
                        VALUES (%s, %s, %s, %s, %s, 'active')
                        ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash, status = 'active', archived_at = NULL
                    """, (user_id, clinic_id, email, f"Synthetic {role_name.title()} {clinic_number.upper()}", hash_password(PASSWORD)))
                    cur.execute("""
                        INSERT INTO user_roles (clinic_id, user_id, role_id, assigned_by)
                        VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
                    """, (clinic_id, user_id, roles[role_name], user_ids.get("owner", user_id)))
                    cur.execute("""
                        INSERT INTO user_branch_scopes (clinic_id, user_id, branch_id)
                        VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """, (clinic_id, user_id, branch_id))

                cur.execute("""
                    INSERT INTO doctor_profiles (id, clinic_id, user_id, public_name, specialty, verification_status, status)
                    VALUES (%s, %s, %s, 'Dr. Vale', 'General medicine', 'verified', 'active')
                    ON CONFLICT (id) DO UPDATE SET status = 'active', archived_at = NULL
                """, (doctor_id, clinic_id, user_ids["doctor"]))
                cur.execute("INSERT INTO doctor_services (clinic_id, doctor_id, service_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (clinic_id, doctor_id, service_id))
                cur.execute("INSERT INTO branch_doctors (clinic_id, branch_id, doctor_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (clinic_id, branch_id, doctor_id))

                patient_ids: list[UUID] = []
                for patient_number, full_name in (("SYN-001", "Amelia Rivera"), ("SYN-002", "Jon Bell"), ("SYN-003", "Mina Cole"), ("SYN-004", "Robin Vale")):
                    patient_id = ident(f"patient-{clinic_number}-{patient_number}")
                    patient_ids.append(patient_id)
                    cur.execute("""
                        INSERT INTO patients (id, clinic_id, patient_number, full_name, normalized_email, status)
                        VALUES (%s, %s, %s, %s, %s, 'active')
                        ON CONFLICT (id) DO UPDATE SET full_name = EXCLUDED.full_name, status = 'active', archived_at = NULL
                    """, (patient_id, clinic_id, patient_number, full_name, f"{patient_number.lower()}@synthetic.example.test"))

                appointment_ids: list[UUID] = []
                statuses = ("confirmed", "checked_in", "requested", "no_show")
                for index, status in enumerate(statuses):
                    appointment_id = ident(f"appointment-{clinic_number}-{index}")
                    appointment_ids.append(appointment_id)
                    starts = today + timedelta(hours=9 + index)
                    ends = starts + timedelta(minutes=30)
                    cur.execute("""
                        INSERT INTO appointments (id, clinic_id, branch_id, doctor_id, service_id, patient_id, starts_at, ends_at, occupancy_start, occupancy_end, status, blocks_time, source, reference, idempotency_key, idempotency_body_hash, policy_snapshot)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, 'staff', %s, %s, repeat('0', 64), '{"synthetic":true}')
                        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at, archived_at = NULL
                    """, (appointment_id, clinic_id, branch_id, doctor_id, service_id, patient_ids[index], starts, ends, starts, ends, status, f"DEMO-{clinic_number.upper()}-{index + 1}", f"demo-{clinic_number}-{index + 1}"))

                for index, appointment_id in enumerate(appointment_ids[:2]):
                    cur.execute("""
                        INSERT INTO queue_entries (id, clinic_id, appointment_id, status, checked_in_at, priority, priority_reason)
                        VALUES (%s, %s, %s, %s, now() - (%s || ' minutes')::interval, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, priority = EXCLUDED.priority
                    """, (ident(f"queue-{clinic_number}-{index}"), clinic_id, appointment_id, "waiting" if index == 0 else "in_consultation", 8 + index * 4, index, "demo priority" if index else None))
                for index, patient_id in enumerate(patient_ids[:3]):
                    cur.execute("""
                        INSERT INTO follow_up_tasks (id, clinic_id, patient_id, appointment_id, assignee_user_id, reason, due_at, priority, status)
                        VALUES (%s, %s, %s, %s, %s, %s, now() + (%s || ' hours')::interval, %s, 'due')
                        ON CONFLICT (id) DO UPDATE SET status = 'due', due_at = EXCLUDED.due_at
                    """, (ident(f"follow-up-{clinic_number}-{index}"), clinic_id, patient_id, appointment_ids[index], user_ids["receptionist"], "Check in after visit", index - 1, "high" if index == 0 else "normal"))
                cur.execute("""
                    INSERT INTO notifications (id, clinic_id, user_id, kind, title, body)
                    VALUES (%s, %s, %s, 'follow_up_due', 'Synthetic follow-up due', 'A demo follow-up needs attention.')
                    ON CONFLICT (id) DO UPDATE SET read_at = NULL
                """, (ident(f"notification-{clinic_number}"), clinic_id, user_ids["receptionist"]))

                # Clinical form template (specialty-agnostic) + a draft response on the first patient.
                form_id = ident(f"form-template-{clinic_number}")
                field_schema = (
                    '{"fields":[' 
                    '{"key":"graft_count","label":"Estimated graft count","type":"number","required":true,"options":[]},' 
                    '{"key":"donor_area","label":"Donor area","type":"select","required":true,"options":["Occipital","Temporal","Beard"]},' 
                    '{"key":"review_on","label":"Review date","type":"date","required":false,"options":[]},' 
                    '{"key":"consent_confirmed","label":"Consent discussed","type":"checkbox","required":false,"options":[]},' 
                    '{"key":"clinical_notes","label":"Clinical notes","type":"textarea","required":false,"options":[]}]}'
                )
                # Clinical-forms tables may be absent on a dev DB that predates that
                # migration; seed them best-effort inside a savepoint so their absence
                # never discards the core demo data the dashboard needs.
                try:
                    with db.transaction():
                        cur.execute("""
                            INSERT INTO clinical_form_templates (id, clinic_id, specialty_id, form_key, name, field_schema, created_by_user_id)
                            VALUES (%s, %s, NULL, 'hair_assessment', 'Hair transplant assessment', CAST(%s AS jsonb), %s)
                            ON CONFLICT (id) DO UPDATE SET field_schema = EXCLUDED.field_schema, status = 'active', archived_at = NULL
                        """, (form_id, clinic_id, field_schema, user_ids["doctor"]))
                        cur.execute("""
                            INSERT INTO clinical_form_responses (id, clinic_id, patient_id, template_id, response_data)
                            VALUES (%s, %s, %s, %s, CAST(%s AS jsonb))
                            ON CONFLICT (id) DO UPDATE SET response_data = EXCLUDED.response_data, status = 'draft'
                        """, (ident(f"form-response-{clinic_number}"), clinic_id, patient_ids[0], form_id, '{"graft_count": 2500, "donor_area": "Occipital"}'))
                except psycopg.errors.UndefinedTable:
                    pass
        db.commit()
    print("Seeded two synthetic clinics: demo-collision-a and demo-collision-b")
    print(f"Synthetic login password: {PASSWORD}")


if __name__ == "__main__":
    main()

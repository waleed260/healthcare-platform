# Field-encryption key rotation

`FIELD_ENCRYPTION_KEYS` accepts a comma-separated keyring. The first Fernet key
encrypts new fields; later keys decrypt existing fields during a staged rotation.
Keys are deployment secrets, never source-controlled values.

1. Generate a new Fernet key in the approved secret manager.
2. Deploy with `FIELD_ENCRYPTION_KEYS=<new-key>,<current-key>` and verify MFA,
   encrypted document metadata, and browser-push subscription reads using only
   synthetic staging data.
3. Run the tenant-scoped `document_metadata_encrypt` worker for each clinic and
   record queued/failed counts. Re-encryption of other encrypted fields requires
   their owning workflow to rewrite them before retiring the old key.
4. After evidence confirms no ciphertext requires the old key, deploy with only
   `<new-key>`. Keep the old key in the secret manager's recovery history for
   the approved retention interval; never add it to logs or runbooks.

If decryption fails, stop the rotation, retain the old key in the active keyring,
and investigate using request IDs only. Do not replace metadata with plaintext.

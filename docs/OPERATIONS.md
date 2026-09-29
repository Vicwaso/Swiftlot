# Swiftlot operating guide

## Configuration

Swiftlot, KES and 0111506710 are the supplied initial business details. The default time zone is Africa/Nairobi. They can be changed by the owner in Website settings. No invented address, stock, reviews, employees or policies are included. Enter real business information and jurisdiction-appropriate, approved privacy and commercial terms before public launch.

Copy `.env.example` to `.env` on the deployment host. Generate a unique random `SECRET_KEY` (at least 50 characters) and a strong PostgreSQL password; never commit this file. Set `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `PUBLIC_ORIGIN` for the real domain. Keep `DEBUG=false` and `MFA_REQUIRED=true` in production. Django refuses to start production without a secret or PostgreSQL database.

`SECRET_KEY` also derives the encryption key for stored authenticator secrets. Back it up separately in a secrets manager. Rotating it without a controlled MFA migration makes existing authenticators unusable. Do not print secrets into tickets or support logs.

## PostgreSQL deployment

The supplied Docker Compose configuration runs PostgreSQL, the web process and a worker. Install Docker on the deployment host, configure `.env`, then:

```text
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py check --deploy
docker compose exec web python manage.py launch_check
```

The first web startup applies database migrations, collects static assets and installs staff roles. The worker may restart until those migrations finish. For future upgrades, back up first, stop the worker, apply migrations once, roll out the web process and restart the worker. Never run migrations concurrently across replicas. Test rollback plans for schema changes on staging.

The backend port is bound to host loopback. Put a maintained HTTPS reverse proxy such as Nginx or Caddy in front of it. Route static assets through Django/WhiteNoise. **Never expose the storage directory directly**: photo and private document routes enforce availability and permissions.

When TLS terminates at a proxy, configure that proxy to discard client-supplied forwarding headers and set `X-Forwarded-Proto` itself. Set `TRUST_PROXY=true` and configure Waitress trusted-proxy settings for that exact proxy. If running a host proxy through Docker's loopback-bound backend, update the Waitress command with `--trusted-proxy=* --trusted-proxy-headers=x-forwarded-proto` only while the backend remains inaccessible to untrusted clients. Otherwise use the actual proxy address. Do not expose an untrusted HTTP backend on the public internet. Redirect HTTP to HTTPS at the proxy.

Set the proxy's upload/body limit high enough for the intended photo batch (up to 20 × 12 MB) while preserving Django's per-file validation. Restrict database access to the application network. Use managed PostgreSQL TLS when the database crosses a network boundary.

The Docker/PostgreSQL configuration is provided for the deployment host. Local development can run without Docker using SQLite. SQLite does not provide the row-lock concurrency guarantees relied on in production.

## Private storage

Local installations store files under `storage/`, persisted with the Docker `vehicle_files` volume. Public photos are decoded, EXIF-orientation corrected, stripped of metadata, resized to a maximum 1920 × 1440 and re-encoded to JPEG. Only staff can upload; public forms never accept files. Private documents are PDF-only, capped at 10 MB, downloaded as attachments and protected by a separate permission.

For S3-compatible private object storage, install `requirements-storage.txt`, then set `S3_BUCKET`, optional `S3_ENDPOINT_URL`, `AWS_DEFAULT_REGION`, and IAM credentials through the platform's secret mechanism. Use bucket-level public access blocking, encryption and least-privilege IAM. The application streams files through its checked routes; do not grant public bucket access or swap image links for long-lived public object URLs. The S3 option requires verification against your chosen provider before launch.

Private PDFs are sent to an internal ClamAV daemon before saving in production. Set `CLAMAV_HOST=scanner` and start Compose with `docker compose --profile document-scanning up --build -d` to enable the supplied scanner service, or configure an existing internal daemon. Keep its virus signatures updated. The scanner port must not be publicly exposed. Production rejects PDF uploads if the scanner is missing, unavailable or reports a threat. Development may accept unscanned PDFs, but those documents cannot be downloaded after switching to production until they are reuploaded and scanned. No active PDF content is rendered inline by the website. Image uploads are decoded and re-encoded as JPEG rather than serving the original uploaded bytes.

## Roles and accounts

Only the owner creates staff accounts. The supplied roles are Inventory manager, Sales agent, Sales manager, Finance officer and Read-only reviewer. Role changes apply on the next request. Disabling a staff member also deletes their active sessions. Owner access is not editable through another staff member's role form.

All staff use password authentication followed by TOTP. There are no default passwords. Use an authenticator app at first login. For lost authenticators, a server owner verifies the person's identity out of band, then runs:

```text
python manage.py reset_mfa USERNAME --confirm
python manage.py changepassword USERNAME
```

The reset invalidates sessions and requires fresh enrolment. The password command is optional if the password was not compromised. Recovery is an operator action, not a public web endpoint.

## Inventory and sales

Publication checks require a verified seller, valid agreement dates, assigned staff, a genuine photo, asking price, specifications and condition/defect disclosure. Only Pending review can become Available. Reserved, Sold, Withdrawn, Archived and Draft stock is hidden.

Mark as sold uses a database transaction and a locked vehicle row. A unique partial database constraint prevents two active sales. Repeated identical confirmation returns the existing sale. Sale reversal requires owner permission, reconciled financial entries and a reason; it returns the vehicle to Pending review. It never republishes automatically.

Availability is read from the database on every public request. Dynamic responses are `no-store`; there is no separate search index or page cache to invalidate. Open connected browser pages recheck availability every 25 seconds and on focus. Requests to sold vehicle URLs return 410 without original details. Public photo endpoints also reject sold records. A browser or external search engine may retain data already downloaded; no website can recall those copies.

## Enquiries and communication

New enquiries are stored before notifications are queued. General enquiries and viewing requests have references and duplicate-submit protection. Staff may add a walk-in buyer directly. A viewing is only confirmed through staff processing; overlapping confirmed appointments for the same agent are rejected. Enquiries for sold vehicles cannot be submitted. Existing viewings are cancelled and other open enquiries flagged for review when a sale commits.

Configure SMTP and the notification recipient in Website settings. Run `python manage.py process_jobs --loop` continuously under a supervisor, or run it once each minute through the host scheduler. Jobs expire reservations and offers, send reservation warnings and retry emails with backoff. Failed sends remain visible. Mail is delivered at least once: a process crash after SMTP acceptance but before the database commit can cause a duplicate notification. Mail failure does not change a sale or discard an enquiry. Customers are not automatically enrolled in marketing.

## Financial records

Commission is a fixed amount or a percentage of final sale price, rounded half-up to two decimals. The rule, payer and notes are copied into the sale. No tax is inferred; record the agreed treatment in the fee notes and obtain the correct local accounting guidance before configuring prices and invoices.

Vehicle proceeds, refunds, separately received commission, retained commission, approved deductions and seller settlements are distinct entries. Seller settlement due is actual proceeds received minus refunds, seller-approved deductions, retained commission and payments already made to the seller. The system rejects allocations above the proceeds held and commission above the amount due. Buyer-paid commission cannot be deducted from seller proceeds. Original entries are kept when reversed. The system records payments; it does not move money or replace a general ledger.

## Backups and restoration

For a small local-storage deployment, generate a Fernet `BACKUP_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, store it securely and separately, pause all writes, then run:

```text
python manage.py backup /secure/path/swiftlot-backup.enc --writes-paused
```

This creates an encrypted compressed database/file backup, excluding sessions and rate-limit counters. It is an in-memory archive intended for small catalogues. Large or S3 deployments should use PostgreSQL's managed/physical backups or `pg_dump` and bucket versioning, with matching timestamps and separately protected encryption keys. Confirm that private documents and deleted-object retention are covered by storage lifecycle rules.

Rehearse recovery into a separate environment. Migrate an empty database, restore the original `SECRET_KEY` and `BACKUP_KEY`, stop web/worker processes, and run:

```text
python manage.py restore_backup /secure/path/swiftlot-backup.enc --confirm-empty-restore
```

The command refuses a database with users, settings or vehicles. Do not run bootstrap first. After restore, check row counts, staff sign-in, private document access and a sold vehicle's absence from public results before reopening. If restoration fails halfway, discard the isolated target and repeat into a new empty database; do not open a partially restored site.

Start with daily encrypted backups and a restore rehearsal before launch; confirm recovery objectives with the business. Monitor backup age, worker uptime, pending/failed notification counts, application errors, disk usage and certificate expiry through the hosting platform.

## Retention and housekeeping

Set a business-approved retention duration in Website settings. `python manage.py anonymize_enquiries` reports eligible old closed enquiries that have never been linked to a sale. Add `--apply` only after reviewing that policy. It scrubs contact details and linked notes without deleting inventory or financial records. Sale-linked buyer records, seller documents and legally retained accounting evidence require a separate authorised retention decision. Audit entries store field-change values for vehicles; exclude personal information from free-text vehicle notes where possible.

Removed photo records become inaccessible immediately. Their orphaned storage objects are retained to avoid deleting files during rolled-back transactions; include periodic orphan cleanup in the storage lifecycle after the agreed retention period. Do not delete files merely because they are absent from a public page.

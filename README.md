# Swiftlot vehicle brokerage website

A Python/Django application with a public vehicle catalogue and a private, role-controlled staff workspace. No invented inventory, reviews, staff or contact details are seeded.

## Run locally on Windows

Requires Python 3.12 or newer. Double-click **Start Swiftlot.cmd**, or run `python start_local.py` from this directory. The launcher installs dependencies, creates a local database, applies migrations and prints a one-time owner setup link. Open that link to choose your own username and password. Sign in at `/staff/login/` and enrol an authenticator app. There is no default password or public account registration. A PowerShell launcher (`start-local.ps1`) is also included.

For macOS/Linux: create a virtual environment, install `requirements.lock`, set `LOCAL_ONLY=true`, run `python manage.py migrate`, `python manage.py bootstrap`, `python manage.py collectstatic --noinput`, then `python manage.py runserver 127.0.0.1:8000`.

Local development uses SQLite for easy setup. Production uses PostgreSQL and rejects SQLite. The Windows startup script also runs the reservation-expiry worker and stops it when you stop the server. On macOS/Linux, run a second terminal with the same environment and `python manage.py process_jobs --loop`. LOCAL_ONLY prevents connections to production database, object-storage and SMTP settings in an existing .env. The development server is local-only and is not a public deployment.

## Your first listing

Website settings also includes **Social media**: enter Facebook, Instagram, TikTok, X and YouTube profile URLs or @handles, and a full LinkedIn profile/company URL. Saved profiles appear on the public footer and contact page; blank entries remain hidden. The light/dark mode button is available in the public navigation and staff sidebar. It follows the device theme initially and remembers a chosen mode in that browser.

1. In Website settings, enter your real business name, default currency, contact details and approved policy text.
2. Add a seller, record the evidence you checked, and mark the seller verified.
3. Choose Vehicles → Add vehicle. Enter specifications, price, condition, known defects, responsible staff member and valid seller agreement dates. Confirm the agreement.
4. Upload genuine photos. Edit captions and positions; the lowest position becomes the cover photo. Private PDFs use a separate upload and download route.
5. Preview the listing, submit it for review, then Publish. Only Available stock is public.
6. Enquiries appear in the staff workspace. For a walk-in buyer, add an enquiry and link it to the vehicle.
7. Choose Mark as sold, select the buyer and enter the final price and evidence. Public lists, photos and direct vehicle URLs stop exposing the vehicle after the sale commits. Old detail URLs return HTTP 410. Private records remain available.

## Included operations

- Search/filter/sort/paginate inventory and responsive vehicle galleries.
- Multi-photo upload, validation, EXIF stripping, compression, descriptions, ordering and removal.
- Staff-only seller, enquiry, viewing, task and offer records; assignment, notes and follow-ups.
- Draft → review → available → reserved/sold/withdrawn → archived lifecycle.
- Reservations with expiry, viewing conflict checks and cancellation on sale.
- Transactional, version-checked sales, fee snapshots, commission rounding and safe retries.
- Receipts, refunds, approved deductions, seller settlements, commission allocation and reversal history.
- Per-currency sales reports, CSV export, operational counts, audit events and durable email retry queue.
- Server-side permissions, staff MFA, login throttling, CSRF protection and private file access.
- Encrypted backup/empty-database restore commands and operator recovery tools.

See `docs/OPERATIONS.md` for deployment, backup and recovery. See `docs/ACCEPTANCE.md` for the test map and deployment limits.

## Tests

```text
DEBUG=true python manage.py test brokerage.tests
```

PowerShell: `$env:DEBUG='true'; python manage.py test brokerage.tests`.
For concurrency integration tests, set `DATABASE_URL` to an isolated PostgreSQL test database and run the same command. Django creates/destroys a test database; the role needs permission to do that. Never point automated tests at a production credential.

## No hidden third side

Consumers browse and enquire without accounts. They cannot upload/edit listings or access staff pages, documents or management actions. Staff links are absent from the consumer navigation, and server permissions protect direct URLs. The private area is at `/staff/`; keeping that path secret is not the access control.

## Before publishing

Supply a domain/hosting account, business identity, currency, actual vehicle data/photos, approved policies and SMTP credentials. Configure PostgreSQL, HTTPS, durable storage, backups and a running worker. Run `python manage.py check --deploy` and `python manage.py launch_check`, then perform a restore rehearsal and browser acceptance checks. No online payment gateway or automatic legal ownership transfer is included.

## Render preview

The included `render.yaml` creates a free web service and a free PostgreSQL database in Frankfurt. It runs migrations, installs roles, serves the website and runs the small notification/expiry worker alongside the web process. On the first deploy, copy the one-time owner setup URL from the Render logs and use it immediately. The URL stops working after the owner account is created.

Render's free database expires after 30 days, and free web services do not support persistent disks. Use this configuration for evaluation only. Before adding real stock, upgrade the database and web service and attach a persistent disk mounted at `/var/data`, with `MEDIA_ROOT=/var/data/storage`, or configure the supplied S3-compatible storage option. Configure email using a provider/port permitted by Render.


Vehicle inquiry alerts are emailed to the active staff member who originally added the vehicle, using their staff account email. Later assignment changes do not change the recipient. Existing creators are recovered from creation audit events. Missing creator email retains an in-app notification; unknown/inactive creators and general contact inquiries use the website notification email. Configure SMTP and run process_jobs for delivery; failed sends retry automatically.

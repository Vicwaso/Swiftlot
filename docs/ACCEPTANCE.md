# Acceptance map

## Automated coverage

`brokerage/tests/test_system.py` checks public page rendering, private-page and management-action access, role restrictions, draft visibility, publication completeness, inventory filtering, sold removal from lists/details/photos/sitemap/availability responses, idempotent sale confirmation, stale edits, stale enquiry rejection, durable enquiries, duplicate submissions, reservation expiry, viewing cancellation, fee snapshots, settlement balances, reversals, image validation, multi-photo upload, photo ordering, private files, deactivated sessions, MFA replay rejection, CSV injection safety and notification failure retention.

The PostgreSQL integration test deliberately runs two concurrent sale confirmations. It is skipped when running under SQLite. Run it on the deployment's PostgreSQL version before launch.

## Browser acceptance

Check desktop and phone layouts, keyboard-only navigation, visible focus, labelled fields and errors, gallery buttons, uploads, form submission and status feedback. Test long vehicle titles, missing optional data, no stock, no matching stock and unavailable vehicles. Genuine production photos must be supplied by the owner; test assets must not be imported as inventory.

## Launch gate

- Real business details and approved policies entered.
- Owner MFA enrolled, staff roles checked, no shared/default password.
- PostgreSQL, HTTPS, private durable file storage and email configured.
- Background worker running and failed-job alerts assigned.
- Tests run with PostgreSQL, plus restore rehearsal completed.
- Sale confirmation tested against an already-open consumer page.
- Public domain, contact link and notification delivery verified.
- Accessibility and performance targets verified on the agreed devices/load profile.

## Deliberate limits

The application is a brokerage management system, not a card-payment processor, escrow platform, vehicle ownership registry or statutory accounting product. It does not invent tax treatment or legal policies. It has no consumer registration, consumer listing-upload portal, fake testimonials or generated vehicle images. External search-engine cache removal cannot be immediate. Optional S3 storage, hosting-provider configuration and SMTP delivery need live-environment verification with the actual credentials.

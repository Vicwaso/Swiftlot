# Verification record

Date: 29 September 2026

## Automated checks completed

- Django system checks: no issues.
- Migration consistency: no pending model changes when checked.
- Python source compilation: passed.
- Application test suite: 36 tests, 35 passed, 1 skipped under local SQLite.
- Encrypted backup and restore: passed in an isolated test database, including restored sold-state exclusion and photo storage references.
- All staff page templates and consumer routes are exercised by the suite.

The skipped test is the simultaneous-sale test requiring real PostgreSQL row locks. The production database, Docker deployment, S3 provider, live SMTP service and ClamAV daemon have not been available in this workspace. Their integration must be verified with the deployment environment. The scanner rejection path is tested using a mocked daemon response.

## Browser inspection completed

- Desktop public stock page and contact form rendered with Swiftlot branding and the supplied telephone number.
- Staff password and authenticator login succeeded in a separate QA database, not the user's working database.
- Staff dashboard and Add vehicle screen inspected at desktop width.
- An initial narrow mobile view was inspected; the filters were then changed to a collapsible panel. The browser connection became unavailable before final phone-size reinspection, so full mobile visual acceptance remains unverified.

No demo vehicles, test buyers or test staff were added to the working database. The separate QA server is not part of the deliverable.

## Social profiles and theme update

Three focused checks passed for social profile normalization, rejection of unsafe or mismatched profile URLs, and rendering of theme controls with no invented social accounts. JavaScript checks passed for device-theme defaults, light/dark switching, saved choice after reload, cross-tab synchronization and browsers that block local storage. The browser connection was unavailable for visual inspection of this update.

## Before public launch

Run the same tests against an isolated PostgreSQL database, `check --deploy`, and `launch_check`. Verify the configured mail recipient, private bucket if used, malware scanning, HTTPS forwarding, responsive layouts and accessibility with the real data. Run performance checks under the agreed user load and restore a backup on the target infrastructure.


Theme switch correction (29 September 2026): verified in the running browser that the dark palette changes the body from white to RGB(21, 34, 29), the pointer and Space key toggle the switch, and dark mode survives reload. Versioned CSS/JS URLs prevent stale cached styles. Node checks cover stored preferences, system defaults, storage denial, cross-tab updates and initialization after DOMContentLoaded.

Vehicle creator notification routing: four tests passed for public submission/idempotency, missing email, inactive creator fallback and worker delivery using a test email backend. Live SMTP is not configured; no actual email delivery claimed.

Mobile layout correction (2 October 2026): verified the inventory and vehicle-detail pages at 320px and 360px browser widths. The document width remained inside the viewport; the photo thumbnails retain their own intentional horizontal scroller. The header, title, price, main image, specifications and enquiry form stack within the phone viewport. Django system checks and the public-page smoke test passed.

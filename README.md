# CISIA slot monitor

Checks the CISIA CEnT-S/TOLC calendar page on a schedule and emails you when a
row that was previously closed/unavailable becomes bookable.

## How it works

- `scraper.py` fetches the calendar page, parses the results table, and compares
  it to `state.json` (the last known status of each row).
- If a row flips from closed → open (or its seat count goes from 0 to positive),
  it sends you an email and prints the details to the workflow log.
- `state.json` is committed back to the repo after every run so the next run
  knows what "changed" means.
- `.github/workflows/check_slots.yml` runs this on a schedule via GitHub Actions.

## Setup

1. **Create a new GitHub repo** and push these files to it (or upload them via
   the GitHub web UI: Add file → Upload files).

2. **Set up an app password for sending email.** If using Gmail:
   - Enable 2-Step Verification on the Google account.
   - Go to https://myaccount.google.com/apppasswords and create an app password.
   - Use `smtp.gmail.com`, port `587`, your Gmail address as `SMTP_USER`, and
     the generated app password as `SMTP_PASS`. (Do NOT use your normal Gmail
     password — it won't work and you shouldn't put it in a secret anyway.)
   Any other SMTP provider (Outlook, a transactional email service, etc.) works
   too — just adjust host/port.

3. **Add repository secrets** (Settings → Secrets and variables → Actions → Secrets):
   - `SMTP_USER` — your email address / SMTP username
   - `SMTP_PASS` — your app password / SMTP password
   - `EMAIL_TO` — where you want alerts sent (can be the same address)

4. **Add repository variables** (same page, "Variables" tab — these aren't
   secret, just config):
   - `SMTP_HOST` — e.g. `smtp.gmail.com`
   - `SMTP_PORT` — e.g. `587`
   - `CALENDAR_URL` — (optional) override the default English CEnT-S calendar URL
   - `FILTER_KEYWORDS` — (optional) comma-separated text to only watch specific
     rows. This matches against the FORMAT, UNIVERSITY, CITY, and REGION columns
     together, so:
     - `home` → only CENT@HOME (remote) rows, skips in-person university sessions
     - `Roma, Milano Bicocca` → only rows for those specific universities
     - `home, Roma` → only CENT@HOME rows in Rome
     Leave unset to watch every row on the page.

5. **Enable Actions** on the repo if prompted, and you're done. You can trigger
   a manual test run from the "Actions" tab → "Check CISIA slots" → "Run workflow".

## Notes and limitations

- GitHub's free scheduled Actions are **best-effort**: the `*/5 * * * *` cron
  can lag by several extra minutes when GitHub's shared runners are busy. For
  a true 1-minute cadence you'd need a small always-on VM with a real cron job
  running this same script instead.
- GitHub automatically **disables scheduled workflows after 60 days of repo
  inactivity** (no commits). Since this workflow commits `state.json` on every
  run, that keeps the repo "active" and the schedule alive automatically.
- The scraper looks for column headers (`STATE`, `SEATS`, `UNIVERSITY`, etc.)
  matching what's currently on the CISIA site. If CISIA changes their page
  layout, you may need to tweak the parsing logic in `scraper.py`.
- Free email inboxes sometimes flag automated SMTP mail as spam — check your
  spam folder after the first real alert.

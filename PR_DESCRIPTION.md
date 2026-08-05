PR Title: Add Dockerfile, entrypoint, healthcheck, and .env.example for containerization

Summary
Adds containerization support and runtime docs for the elite-safari-bot application.

What this PR does
- Adds a Dockerfile that:
  - Uses python:3.11-slim
  - Installs requirements.txt
  - Adds a HEALTHCHECK that pings /health
  - Runs the app with gunicorn
  - Uses an entrypoint to support credentials decoding
- Adds entrypoint.sh:
  - Decodes GOOGLE_CREDENTIALS_JSON (base64) into credentials.json at container start (if provided)
- Adds .env.example documenting required environment variables and how to provide Google credentials
- Extends README.md with docker build/run instructions and notes about credentials and production hardening

Files changed / added
- Added: Dockerfile
- Added: entrypoint.sh
- Added: .env.example
- Updated: README.md (added docker/run instructions and notes)

Rationale
- Make the app easier to run locally, in CI, and on container platforms (Heroku, Render, Railway, Docker)
- Avoid requiring file mounts for Google service credentials by supporting a base64-encoded env var
- Provide a healthcheck to enable container orchestrators to detect readiness/failures

Important notes & recommendations (pre-merge)
- VERIFY_TOKEN should be rotated in production — do not rely on the default value.
- The /admin endpoint is not authenticated; add auth before exposing publicly.
- The app currently uses oauth2client for Google Sheets; consider migrating to google-auth (google.oauth2.service_account.Credentials) in a follow-up PR.
- Add Paystack webhook signature verification (PAYSTACK_SECRET) in a follow-up PR.
- Keep credentials.json out of the repo; use secrets in your deployment platform.

How to run & test locally
1) Build
   docker build -t elite-safari-bot:latest .
2) Run (mount credentials.json)
   docker run --rm -p 5000:5000 --env-file .env -v "$(pwd)/credentials.json:/app/credentials.json" elite-safari-bot:latest
3) Or run using base64 credentials (avoid file mounts)
   export GOOGLE_CREDENTIALS_JSON=$(base64 -w0 credentials.json)
   # add GOOGLE_CREDENTIALS_JSON and other vars to .env, then:
   docker run --rm -p 5000:5000 --env-file .env elite-safari-bot:latest
4) Verify:
   curl http://localhost:5000/health

Testing checklist (please confirm before merging)
- [ ] Docker image builds successfully with docker build
- [ ] Container starts and /health returns 200
- [ ] GOOGLE_CREDENTIALS_JSON decoding writes a valid credentials.json when provided
- [ ] App logs show successful startup (no missing dependency errors)
- [ ] Ensure no secrets are committed
- [ ] Optionally: run a quick smoke test of a webhook POST to /webhook (mock payload) and check app logs

Suggested reviewers
- @DdibaMusege (repo owner)

Suggested labels
- enhancement
- infra

PR creation commands

1) Create via web (one-click)
- Open:
  https://github.com/DdibaMusege/elite-safari-bot/compare/main...add-dockerfile-and-env?expand=1
- Click "Create pull request", paste the body above and submit.

2) Create with gh CLI
- Run (single-line with proper quoting):
  gh pr create --base main --head add-dockerfile-and-env --title "Add Dockerfile, entrypoint, healthcheck, and .env.example for containerization" --body "$(sed -n '1,200p' PR_DESCRIPTION.md)"

3) Create with curl (replace GITHUB_TOKEN)
- Run:
  curl -X POST -H "Authorization: token GITHUB_TOKEN" -H "Accept: application/vnd.github+json" \
    https://api.github.com/repos/DdibaMusege/elite-safari-bot/pulls \
    -d '{"title":"Add Dockerfile, entrypoint, healthcheck, and .env.example for containerization","head":"add-dockerfile-and-env","base":"main","body":"Adds containerization support and runtime docs for the elite-safari-bot application.\n\nFiles changed:\n- Dockerfile\n- entrypoint.sh\n- .env.example\n- README.md\n\nSee PR description for usage and testing checklist."}'

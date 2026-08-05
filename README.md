# elite-safari-bot

A simple Flask-based WhatsApp bot for booking Uganda safaris. This branch adds containerization support and an entrypoint that supports providing Google Sheets credentials via a base64 environment variable.

## Docker build & run

Build the image:

    docker build -t elite-safari-bot:latest .

Run the container (mount credentials.json and provide env file):

    docker run --rm -p 5000:5000 --env-file .env -v "$(pwd)/credentials.json:/app/credentials.json" elite-safari-bot:latest

Run the container without mounting the file by using base64-encoded credentials:

    export GOOGLE_CREDENTIALS_JSON=$(base64 -w0 credentials.json)
    # add GOOGLE_CREDENTIALS_JSON and other vars to .env, then:
    docker run --rm -p 5000:5000 --env-file .env elite-safari-bot:latest

The container exposes a health endpoint at `http://localhost:5000/health`.

## Environment variables
See `.env.example` for a full list. The important ones are:

- WHATSAPP_TOKEN and PHONE_NUMBER_ID — Meta/WhatsApp API credentials
- PAYSTACK_SECRET — used to validate Paystack webhooks (not yet implemented)
- OPENAI_API_KEY — enables AI image generation
- VERIFY_TOKEN — webhook verification token (change in production)
- GOOGLE_CREDENTIALS_JSON or credentials.json mount — required for Google Sheets integration

## Notes
- The app currently expects the Google Sheets service account JSON to be present at `/app/credentials.json`. Use either a file mount or set `GOOGLE_CREDENTIALS_JSON` (base64) to avoid mounting files.
- For production, rotate `VERIFY_TOKEN` and secure access to the `/admin` dashboard.

## Next recommended steps
- Add GitHub Actions for linting and a small smoke test.
- Implement Paystack signature verification in `paystack_webhook`.
- Move Google Sheets auth from oauth2client to `google-auth` for long-term compatibility.

#!/bin/sh
set -e

# If GOOGLE_CREDENTIALS or GOOGLE_CREDENTIALS_JSON is provided, write it to the credentials path.
CRED_PATH="${GOOGLE_CREDENTIALS_PATH:-/app/credentials.json}"

if [ -n "${GOOGLE_CREDENTIALS}" ]; then
  echo "Writing GOOGLE_CREDENTIALS (raw JSON) to ${CRED_PATH}"
  printf "%s" "${GOOGLE_CREDENTIALS}" > "${CRED_PATH}"
  echo "Wrote Google credentials to ${CRED_PATH}"
elif [ -n "${GOOGLE_CREDENTIALS_JSON}" ]; then
  echo "Decoding GOOGLE_CREDENTIALS_JSON (base64) to ${CRED_PATH}"
  printf "%s" "${GOOGLE_CREDENTIALS_JSON}" | base64 -d > "${CRED_PATH}"
  echo "Wrote Google credentials to ${CRED_PATH}"
fi

# Execute the passed command (gunicorn via Procfile or Docker CMD)
exec "$@"

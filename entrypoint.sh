#!/bin/sh
set -e

# If GOOGLE_CREDENTIALS_JSON is provided (base64), decode it to the credentials path.
if [ -n "${GOOGLE_CREDENTIALS_JSON}" ]; then
  CRED_PATH="${GOOGLE_CREDENTIALS_PATH:-/app/credentials.json}"
  echo "Decoding GOOGLE_CREDENTIALS_JSON to ${CRED_PATH}"
  printf "%s" "${GOOGLE_CREDENTIALS_JSON}" | base64 -d > "${CRED_PATH}"
  echo "Wrote Google credentials to ${CRED_PATH}"
fi

# Run the requested command
exec "$@"

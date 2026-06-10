#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-open-claw-project-487803}"
REGION="${REGION:-asia-northeast3}"
SERVICE="${SERVICE:-lux-ru}"
ENV_FILE="${ENV_FILE:-.env}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-415500942280-compute@developer.gserviceaccount.com}"

KRX_ID_SECRET="${KRX_ID_SECRET:-krx-id}"
KRX_PW_SECRET="${KRX_PW_SECRET:-krx-pw}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Create it from .env.example first." >&2
  exit 1
fi

read_env_value() {
  local key="$1"
  python3 - "$ENV_FILE" "$key" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
target = sys.argv[2]
value = ""
for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, val = line.split("=", 1)
    if key.strip() != target:
        continue
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    value = val
print(value, end="")
PY
}

require_value() {
  local key="$1"
  local value
  value="$(read_env_value "$key")"
  if [[ -z "$value" ]]; then
    echo "$key is empty in $ENV_FILE" >&2
    exit 1
  fi
  printf '%s' "$value"
}

upsert_secret() {
  local secret_name="$1"
  local secret_file="$2"

  if gcloud secrets describe "$secret_name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets versions add "$secret_name" \
      --data-file="$secret_file" \
      --project="$PROJECT_ID" >/dev/null
    echo "Updated Secret Manager secret: $secret_name"
  else
    gcloud secrets create "$secret_name" \
      --replication-policy=automatic \
      --data-file="$secret_file" \
      --project="$PROJECT_ID" >/dev/null
    echo "Created Secret Manager secret: $secret_name"
  fi

  gcloud secrets add-iam-policy-binding "$secret_name" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" \
    --quiet >/dev/null
}

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
chmod 700 "$tmp_dir"

krx_id_file="$tmp_dir/KRX_ID"
krx_pw_file="$tmp_dir/KRX_PW"
require_value "KRX_ID" > "$krx_id_file"
require_value "KRX_PW" > "$krx_pw_file"
chmod 600 "$krx_id_file" "$krx_pw_file"

upsert_secret "$KRX_ID_SECRET" "$krx_id_file"
upsert_secret "$KRX_PW_SECRET" "$krx_pw_file"

gcloud run deploy "$SERVICE" \
  --source . \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --timeout=600 \
  --quiet \
  --update-secrets="KRX_ID=${KRX_ID_SECRET}:latest,KRX_PW=${KRX_PW_SECRET}:latest"

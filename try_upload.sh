#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_FILE_PATH="${SCRIPT_DIR}/test_doc/dog.jpg"

DOC_SERVER_URL="${DOC_SERVER_URL:-http://127.0.0.1:18055}"
KB_ID="${KB_ID:-__default__}"
ALGO_ID="${ALGO_ID:-general_algo}"
GROUP="${GROUP:-image}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-120}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
CHECK_NORMALIZED_FILE="${CHECK_NORMALIZED_FILE:-0}"
ALGO_CONTAINER="${ALGO_CONTAINER:-lazyrag-alt-lazyllm-algo-1}"

usage() {
  cat <<'EOF'
Usage:
  ./try_upload.sh [image_file]

Environment:
  DOC_SERVER_URL         Default: http://127.0.0.1:18055
  KB_ID                  Default: __default__
  ALGO_ID                Default: general_algo
  GROUP                  Default: image
  TIMEOUT_SECONDS        Default: 120
  POLL_INTERVAL          Default: 2
  CHECK_NORMALIZED_FILE  Default: 0
  ALGO_CONTAINER         Default: lazyrag-alt-lazyllm-algo-1

Examples:
  ./try_upload.sh
  ./try_upload.sh /home/mnt/cuishaoting/LazyRAG/test_doc/猫.jpg
  DOC_SERVER_URL=http://127.0.0.1:18055 KB_ID=demo ./try_upload.sh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 1 ]]; then
  echo "Only one positional argument is supported: image_file" >&2
  usage >&2
  exit 2
fi

FILE_PATH="${1:-${FILE_PATH:-$DEFAULT_FILE_PATH}}"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

pretty_json() {
  local json_file="$1"
  python3 - "$json_file" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
try:
    data = json.loads(text)
except Exception:
    print(text)
else:
    print(json.dumps(data, ensure_ascii=False, indent=2))
PY
}

perform_request() {
  local body_file="$1"
  shift

  local http_code
  http_code="$(curl -sS -o "$body_file" -w '%{http_code}' "$@")"
  if [[ ! "$http_code" =~ ^2 ]]; then
    echo "Request failed with HTTP ${http_code}" >&2
    pretty_json "$body_file" >&2
    return 1
  fi
}

require_cmd curl
require_cmd python3

if [[ ! -f "$FILE_PATH" ]]; then
  echo "Image file not found: $FILE_PATH" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

health_json="${TMP_DIR}/health.json"
groups_json="${TMP_DIR}/groups.json"
upload_json="${TMP_DIR}/upload.json"
task_json="${TMP_DIR}/task.json"
doc_json="${TMP_DIR}/doc.json"
chunks_json="${TMP_DIR}/chunks.json"

echo "[1/6] Checking doc service health: ${DOC_SERVER_URL}/v1/health"
perform_request "$health_json" "${DOC_SERVER_URL}/v1/health"
python3 - "$health_json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
payload = data.get("data") or {}
deps = payload.get("deps") or {}
if payload.get("status") != "ok":
    raise SystemExit("Doc service health status is not ok")
if deps.get("parser") is not True:
    raise SystemExit("Doc service parser dependency is not healthy")
print("Health check passed")
PY

echo "[2/6] Checking algorithm groups: ${DOC_SERVER_URL}/v1/algo/${ALGO_ID}/groups"
perform_request "$groups_json" "${DOC_SERVER_URL}/v1/algo/${ALGO_ID}/groups"
python3 - "$groups_json" "$GROUP" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
groups = data.get("data") or []
names = [item.get("name") for item in groups if isinstance(item, dict)]
print("Available groups:", ", ".join(names) or "<none>")
if sys.argv[2] not in names:
    raise SystemExit(f"Required group not found: {sys.argv[2]}")
PY

echo "[3/6] Uploading image: $FILE_PATH"
perform_request "$upload_json" \
  -X POST "${DOC_SERVER_URL}/v1/docs/upload" \
  -F "kb_id=${KB_ID}" \
  -F "algo_id=${ALGO_ID}" \
  -F "files=@${FILE_PATH}"
pretty_json "$upload_json"

mapfile -t upload_fields < <(python3 - "$upload_json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = ((data.get("data") or {}).get("items") or [])
if not items:
    raise SystemExit("Upload response does not contain data.items")
item = items[0]
doc_id = item.get("doc_id")
task_id = item.get("task_id")
accepted = item.get("accepted")
parse_status = item.get("parse_status")
if not doc_id:
    raise SystemExit("Upload response does not contain doc_id")
if not task_id:
    raise SystemExit("Upload response does not contain task_id")
print(doc_id)
print(task_id)
print(str(bool(accepted)).lower())
print(parse_status or "")
PY
)

DOC_ID="${upload_fields[0]}"
TASK_ID="${upload_fields[1]}"
ACCEPTED="${upload_fields[2]}"
PARSE_STATUS="${upload_fields[3]}"

if [[ "$ACCEPTED" != "true" ]]; then
  echo "Upload was not accepted by doc service" >&2
  exit 1
fi

echo "Accepted upload: doc_id=${DOC_ID} task_id=${TASK_ID} initial_parse_status=${PARSE_STATUS:-<empty>}"

echo "[4/6] Polling task status"
deadline=$((SECONDS + TIMEOUT_SECONDS))
while true; do
  perform_request "$task_json" "${DOC_SERVER_URL}/v1/tasks/${TASK_ID}"
  TASK_STATUS="$(python3 - "$task_json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
payload = data.get("data") or {}
print(payload.get("status") or "")
PY
)"

  if [[ -z "$TASK_STATUS" ]]; then
    echo "Task response does not contain status" >&2
    pretty_json "$task_json" >&2
    exit 1
  fi

  echo "Current task status: ${TASK_STATUS}"
  case "$TASK_STATUS" in
    SUCCESS)
      break
      ;;
    FAILED|CANCELED)
      echo "Task ended unsuccessfully: ${TASK_STATUS}" >&2
      pretty_json "$task_json" >&2
      exit 1
      ;;
  esac

  if (( SECONDS >= deadline )); then
    echo "Timed out waiting for task completion" >&2
    pretty_json "$task_json" >&2
    exit 1
  fi
  sleep "$POLL_INTERVAL"
done

echo "[5/6] Fetching document detail"
perform_request "$doc_json" "${DOC_SERVER_URL}/v1/docs/${DOC_ID}"
python3 - "$doc_json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
payload = data.get("data") or {}
doc = payload.get("doc") or {}
snapshot = payload.get("snapshot") or {}
latest_task = payload.get("latest_task") or {}
print(
    "Document detail:",
    json.dumps(
        {
            "doc_id": doc.get("doc_id"),
            "filename": doc.get("filename"),
            "upload_status": doc.get("upload_status"),
            "snapshot_status": snapshot.get("status"),
            "latest_task_id": latest_task.get("task_id"),
        },
        ensure_ascii=False,
    ),
)
PY

echo "[6/6] Fetching chunks from group=${GROUP}"
perform_request "$chunks_json" \
  -G "${DOC_SERVER_URL}/v1/chunks" \
  --data-urlencode "kb_id=${KB_ID}" \
  --data-urlencode "algo_id=${ALGO_ID}" \
  --data-urlencode "doc_id=${DOC_ID}" \
  --data-urlencode "group=${GROUP}" \
  --data-urlencode "page_size=20"
pretty_json "$chunks_json"

mapfile -t chunk_fields < <(python3 - "$chunks_json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
payload = data.get("data") or {}
items = payload.get("items") or []

has_file_type = False
has_is_pure_image = False
normalized_source_path = ""

for item in items:
    for meta in (item.get("metadata") or {}, item.get("global_metadata") or {}):
        if meta.get("file_type") == "image":
            has_file_type = True
        if meta.get("is_pure_image") is True:
            has_is_pure_image = True
        if not normalized_source_path and meta.get("normalized_source_path"):
            normalized_source_path = meta["normalized_source_path"]

print(len(items))
print("true" if has_file_type else "false")
print("true" if has_is_pure_image else "false")
print(normalized_source_path)
PY
)

CHUNK_COUNT="${chunk_fields[0]}"
HAS_FILE_TYPE="${chunk_fields[1]}"
HAS_IS_PURE_IMAGE="${chunk_fields[2]}"
NORMALIZED_SOURCE_PATH="${chunk_fields[3]}"

if [[ "$CHUNK_COUNT" == "0" ]]; then
  echo "No chunks were produced for group=${GROUP}" >&2
  exit 1
fi

if [[ "$HAS_FILE_TYPE" != "true" ]]; then
  echo "Chunks do not contain metadata.file_type=image" >&2
  exit 1
fi

if [[ "$HAS_IS_PURE_IMAGE" != "true" ]]; then
  echo "Chunks do not contain metadata.is_pure_image=true" >&2
  exit 1
fi

if [[ -z "$NORMALIZED_SOURCE_PATH" ]]; then
  echo "Chunks do not contain normalized_source_path" >&2
  exit 1
fi

if [[ "$CHECK_NORMALIZED_FILE" == "1" ]]; then
  require_cmd docker
  echo "Checking normalized file inside container ${ALGO_CONTAINER}: ${NORMALIZED_SOURCE_PATH}"
  if ! docker exec "$ALGO_CONTAINER" sh -lc 'test -f "$1"' sh "$NORMALIZED_SOURCE_PATH"; then
    echo "Normalized file not found in container ${ALGO_CONTAINER}" >&2
    exit 1
  fi
fi

echo
echo "Upload verification passed"
echo "  file: ${FILE_PATH}"
echo "  kb_id: ${KB_ID}"
echo "  algo_id: ${ALGO_ID}"
echo "  doc_id: ${DOC_ID}"
echo "  task_id: ${TASK_ID}"
echo "  group: ${GROUP}"
echo "  chunk_count: ${CHUNK_COUNT}"
echo "  normalized_source_path: ${NORMALIZED_SOURCE_PATH}"

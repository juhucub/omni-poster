#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-deploy/compose/docker-compose.yml}"
API_BASE="${API_BASE:-http://localhost:8000}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-600}"
POLL_SECONDS="${POLL_SECONDS:-5}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/omniposter-mvp-smoke.XXXXXX")"
COOKIE_JAR="$TMP_DIR/cookies.txt"
REPORT="$TMP_DIR/report.txt"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" | tee -a "$REPORT"
  exit 1
}

note() {
  echo "$*" | tee -a "$REPORT"
}

json_get() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
path = sys.argv[2].split(".") if sys.argv[2] else []
value = payload
for part in path:
    if part.isdigit():
        value = value[int(part)]
    else:
        value = value.get(part)
    if value is None:
        break
if isinstance(value, (dict, list)):
    print(json.dumps(value))
elif value is None:
    print("")
else:
    print(value)
PY
}

curl_json() {
  curl -fsS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -H "Content-Type: application/json" "$@"
}

curl_form() {
  curl -fsS -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$@"
}

cd "$ROOT_DIR"

note "OmniPoster MVP smoke verification"
note "Compose file: $COMPOSE_FILE"
note "API: $API_BASE"

docker compose -f "$COMPOSE_FILE" ps >/tmp/omniposter_mvp_compose_ps.txt || fail "docker compose ps failed"
note "Docker compose services:"
cat /tmp/omniposter_mvp_compose_ps.txt | tee -a "$REPORT"

health="$(curl -fsS "$API_BASE/health/deep")" || fail "/health/deep failed"
status_value="$(json_get "$health" "status")"
openvoice_reason="$(json_get "$health" "checks.openvoice.reason")"
fallback_ok="$(json_get "$health" "checks.tts_fallback.ok")"
note "Deep health status: $status_value"
note "Fallback TTS available: $fallback_ok"
note "OpenVoice reason: ${openvoice_reason:-available}"

username="smoke_$(date +%s)"
password="Password1"
auth_payload="{\"username\":\"$username\",\"password\":\"$password\"}"
curl_json -X POST "$API_BASE/auth/register" -d "$auth_payload" >/dev/null || fail "register smoke user failed"

project_payload="{\"name\":\"MVP Smoke $(date +%H%M%S)\",\"target_platform\":\"youtube\"}"
project="$(curl_json -X POST "$API_BASE/projects" -d "$project_payload")" || fail "create project failed"
project_id="$(json_get "$project" "id")"
note "Project id: $project_id"

script_payload='{"parsed_lines":[{"speaker":"Host","text":"This is a smoke test for the full render pipeline.","order":0},{"speaker":"Guest","text":"It should produce audio, video, artifacts, and a downloadable MP4.","order":1}],"source":"mvp_smoke"}'
curl_json -X PUT "$API_BASE/projects/$project_id/script" -d "$script_payload" >/dev/null || fail "save script failed"

portrait_file="$TMP_DIR/portrait.png"
python3 - "$portrait_file" <<'PY'
import base64
import sys
png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
open(sys.argv[1], "wb").write(base64.b64decode(png))
PY

create_character() {
  local name="$1"
  local voice="$2"
  local payload
  payload=$(python3 - "$name" "$voice" <<'PY'
import json, sys
name, voice = sys.argv[1], sys.argv[2]
print(json.dumps({
    "display_name": name,
    "speaker_names": [name],
    "tts_provider": "espeak",
    "fallback_provider": "espeak",
    "voice": voice,
    "rate": 155,
    "pitch": 45,
    "word_gap": 1,
    "amplitude": 140,
    "sample_text": f"{name} speaks in the MVP smoke verification.",
}))
PY
)
  local character
  character="$(curl_json -X POST "$API_BASE/character-presets" -d "$payload")" || fail "create $name character failed"
  local character_id
  character_id="$(json_get "$character" "id")"
  curl_form -X POST "$API_BASE/character-presets/$character_id/portrait" -F "file=@$portrait_file;type=image/png" >/dev/null || fail "upload $name portrait failed"
  echo "$character_id"
}

host_character="$(create_character Host en-us+f3)"
guest_character="$(create_character Guest en-gb+m3)"
bindings_payload="$(python3 - "$host_character" "$guest_character" <<'PY'
import json, sys
print(json.dumps({"items": [
    {"speaker_name": "Host", "character_preset_id": sys.argv[1]},
    {"speaker_name": "Guest", "character_preset_id": sys.argv[2]},
]}))
PY
)"
curl_json -X PUT "$API_BASE/projects/$project_id/speaker-bindings" -d "$bindings_payload" >/dev/null || fail "bind speakers failed"

presets="$(curl -fsS "$API_BASE/background-presets")" || fail "list background presets failed"
preset_key="$(python3 - "$presets" <<'PY'
import json, sys
items = json.loads(sys.argv[1])
print(items[0]["key"] if items else "")
PY
)"
if [[ -n "$preset_key" ]]; then
  preset_key_url="$(python3 - "$preset_key" <<'PY'
from urllib.parse import quote
import sys
print(quote(sys.argv[1], safe=""))
PY
)"
  curl_json -X POST "$API_BASE/projects/$project_id/assets/background/preset/$preset_key_url" -d '{}' >/dev/null || fail "select background preset failed"
  note "Background preset: $preset_key"
else
  command -v ffmpeg >/dev/null || fail "no background preset available and host ffmpeg missing"
  bg_file="$TMP_DIR/background.mp4"
  ffmpeg -hide_banner -loglevel error -y -f lavfi -i color=c=0x101827:s=540x960:d=4 -pix_fmt yuv420p "$bg_file"
  curl_form -X POST "$API_BASE/projects/$project_id/assets/background" -F "file=@$bg_file;type=video/mp4" >/dev/null || fail "upload generated background failed"
  note "Background upload: generated color MP4"
fi

job="$(curl_json -X POST "$API_BASE/projects/$project_id/renders" -d '{"output_kind":"draft","background_style":"none","provider_name":"local-compositor"}')" || fail "queue render failed"
job_id="$(json_get "$job" "id")"
note "Generation job id: $job_id"

deadline=$((SECONDS + TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  job="$(curl_json "$API_BASE/generation-jobs/$job_id")" || fail "poll job failed"
  job_status="$(json_get "$job" "status")"
  progress="$(json_get "$job" "progress")"
  note "Job status: $job_status ${progress}%"
  case "$job_status" in
    completed|failed|canceled) break ;;
  esac
  sleep "$POLL_SECONDS"
done

[[ "$job_status" == "completed" ]] || fail "render did not complete; final status=$job_status error=$(json_get "$job" "error_message")"

artifacts="$(curl_json "$API_BASE/generation-jobs/$job_id/artifacts")" || fail "artifact summary failed"
segment_count="$(python3 - "$artifacts" <<'PY'
import json, sys
print(len(json.loads(sys.argv[1]).get("segment_wavs") or []))
PY
)"
[[ "$segment_count" -gt 0 ]] || fail "no segment WAV artifacts reported"

outputs="$(curl_json "$API_BASE/projects/$project_id/outputs")" || fail "list outputs failed"
output_url="$(python3 - "$outputs" <<'PY'
import json, sys
items = json.loads(sys.argv[1]).get("items") or []
print((items[0].get("asset") or {}).get("content_url") or "")
PY
)"
[[ -n "$output_url" ]] || fail "no output MP4 URL found"

mp4_path="$TMP_DIR/output.mp4"
curl -fsS -b "$COOKIE_JAR" "$API_BASE$output_url" -o "$mp4_path" || fail "download output MP4 failed"
[[ -s "$mp4_path" ]] || fail "downloaded MP4 is empty"
command -v ffprobe >/dev/null || fail "host ffprobe missing"
duration="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$mp4_path")" || fail "ffprobe duration failed"
video_streams="$(ffprobe -v error -select_streams v -show_entries stream=codec_type -of csv=p=0 "$mp4_path" | wc -l | tr -d ' ')"
audio_streams="$(ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$mp4_path" | wc -l | tr -d ' ')"
python3 - "$duration" <<'PY' || fail "MP4 duration is not > 0"
import sys
sys.exit(0 if float(sys.argv[1]) > 0 else 1)
PY
[[ "$video_streams" -gt 0 ]] || fail "MP4 has no video stream"
[[ "$audio_streams" -gt 0 ]] || fail "MP4 has no audio stream"

providers="$(python3 - "$artifacts" <<'PY'
import json, sys
segments = json.loads(sys.argv[1]).get("segment_wavs") or []
print(", ".join(f"{s.get('speaker')}={s.get('provider_used')}" for s in segments))
PY
)"
note "Segment providers: $providers"
note "Output URL: $output_url"
note "Downloaded MP4: $mp4_path"
note "ffprobe duration: $duration"
note "video streams: $video_streams"
note "audio streams: $audio_streams"
note "PASS: MVP smoke verification completed"

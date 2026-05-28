#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'repo hygiene failed: %s\n' "$1" >&2
  exit 1
}

tracked_files="$(git ls-files)"

duplicate_files="$(printf '%s\n' "$tracked_files" | grep -E '(^|/).*( copy| [0-9]+)\.[A-Za-z0-9]+$|\.bak$|\.old$' || true)"
if [[ -n "$duplicate_files" ]]; then
  printf '%s\n' "$duplicate_files" >&2
  fail "tracked duplicate/copy files are not allowed"
fi

tracked_generated_media="$(printf '%s\n' "$tracked_files" | grep -E '(^|/)(generated_videos|backend/generated_videos)/|^backend/storage/generated/|^backend/storage/render_cache/|\.(mp4|mov|avi|mkv|webm|wav|m4a|aac|flac|ogg)$' || true)"
if [[ -n "$tracked_generated_media" ]]; then
  printf '%s\n' "$tracked_generated_media" >&2
  fail "tracked generated media is not allowed"
fi

tracked_databases="$(printf '%s\n' "$tracked_files" | grep -E '\.(sqlite|sqlite3|db)(-journal)?$|celerybeat-schedule' || true)"
if [[ -n "$tracked_databases" ]]; then
  printf '%s\n' "$tracked_databases" >&2
  fail "tracked local databases or Celery schedule files are not allowed"
fi

tracked_frontend_artifacts="$(printf '%s\n' "$tracked_files" | grep -E '^frontend/(build|dist|playwright-report|test-results|blob-report)/' || true)"
if [[ -n "$tracked_frontend_artifacts" ]]; then
  printf '%s\n' "$tracked_frontend_artifacts" >&2
  fail "tracked frontend build/test artifacts are not allowed"
fi

tracked_backend_runtime="$(printf '%s\n' "$tracked_files" | grep -E '^backend/backend/|^runtime/' || true)"
if [[ -n "$tracked_backend_runtime" ]]; then
  printf '%s\n' "$tracked_backend_runtime" >&2
  fail "tracked runtime/backend runtime folders are not allowed"
fi

tracked_model_artifacts="$(printf '%s\n' "$tracked_files" | grep -E '^vendor/OpenVoice/checkpoints|^backend/storage/voice_models/.+\.(pth|pt|ckpt|onnx|bin|safetensors|index|json|md5|wav|mp3|flac|m4a|gitattributes)$' || true)"
tracked_model_artifacts="$(printf '%s\n' "$tracked_model_artifacts" | grep -Ev '(^$|/README\.md$|/\.gitkeep$)' || true)"
if [[ -n "$tracked_model_artifacts" ]]; then
  printf '%s\n' "$tracked_model_artifacts" >&2
  fail "tracked voice model/checkpoint/runtime artifacts are not allowed"
fi

printf 'repo hygiene ok\n'

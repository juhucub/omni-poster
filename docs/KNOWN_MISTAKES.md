# Known Mistakes - Active High-Risk Rules

## Always Relevant
- Do not touch .git.
- Do not mark complete without evidence.
- Do not commit generated media/model artifacts.
- Keep docs updates small and evidence-based.
- Do not run pytest processes that share the repository SQLite test database in parallel; use sequential backend test commands or isolated DB paths to avoid misleading `attempt to write a readonly database` setup errors.
- Do not rely on process-local rate limiting in production; production limits must use a durable shared backend and fail closed when that backend is unavailable.

## TTS / Voice / Rendering
- Do not silently replace selected OpenVoice/XTTS profiles.
- Do not use hidden temp segment audio.
- Final MP4 must use persisted segment WAVs.
- Do not satisfy XTTS/OpenVoice render jobs from Voice Lab preview audio or loose shared audio caches.
- XTTS/OpenVoice rendered segment audio may be reused only through the strict content-addressed render cache when all text, voice profile, provider, reference, recipe, and render settings inputs match.
- XTTS worker runtime reuse may cache loaded models/config/checkpoints and conditioning latents, but must not bypass the render cache provenance rules for segment WAV reuse.
- Preview-only XTTS inference shortcuts must stay opt-in and must not silently change export voice quality.
- Verify provider availability in Docker.
- Do not "optimize" render jobs by reusing Voice Lab preview audio or shared preview caches for final render segments.
- Do not raise Celery generation concurrency blindly for CPU-only XTTS; profile first and prefer one generation worker process when CPU/RAM pressure is high.
- Do not assume the XTTS worker runtime cache is shared across Celery prefork processes; each process can load its own model and consume several GB of RSS.
- Do not rewrite the renderer or provider path for performance before checking `generation_profile.json` and preserving persisted segment WAV assembly.
- Do not run heavy Voice Lab reference processing, dataset analysis, model attach, profile preparation, or calibration candidate synthesis inside FastAPI request handlers; queue it to `voice_worker`.
- Do not reintroduce whole-file `Path.read_bytes()`/in-memory copies for staged Voice Lab reference uploads in worker jobs; stream/copy from the staged file path and let ffmpeg normalize from disk.

## Assets
- Character assets must not come from background preset directories.
- Background presets must be discovered from the configured preset path.
- Do not trust `UploadFile.content_type` alone for media uploads; validate declared MIME types against file headers and keep explicit size/quota/duration limits.
- Do not read imported script uploads with an unbounded whole-file `read()`; enforce extension, MIME, size, and UTF-8 checks before saving a revision.
- Regression coverage now includes `backend/app/tests/test_vertical_slice.py::test_character_images_are_not_loaded_from_background_preset_directories` and `test_background_presets_are_loaded_from_bundled_media_dir`.

## Script Generation
- Do not duplicate hardcoded content format lists across backend and frontend. The backend content format registry is the source of truth; frontend fallback constants are only for API-unavailable resilience and must stay aligned with registry tests.
- Do not cache provider-failure fallback scripts as if they were successful model generations; a temporary Ollama outage must not freeze static output for future requests.
- Debate format fallback must stay topic-grounded through normalized sides; do not reintroduce placeholder examples such as "Two characters debate", unrelated cats-or-dogs canned topics, generic workflow/speed/review boilerplate, or word-budget trimming that leaves incomplete sentence fragments.

## When More Detail Is Needed
Read docs/archive/KNOWN_MISTAKES_ARCHIVE.md.

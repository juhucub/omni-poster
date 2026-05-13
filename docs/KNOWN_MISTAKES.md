# Known Mistakes - Active High-Risk Rules

## Always Relevant
- Do not touch .git.
- Do not mark complete without evidence.
- Do not commit generated media/model artifacts.
- Keep docs updates small and evidence-based.

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
- Regression coverage now includes `backend/app/tests/test_vertical_slice.py::test_character_images_are_not_loaded_from_background_preset_directories` and `test_background_presets_are_loaded_from_bundled_media_dir`.

## When More Detail Is Needed
Read docs/archive/KNOWN_MISTAKES_ARCHIVE.md.

# Render Domain

This package owns render-domain decisions that are safe to share across routers, workers, and the renderer:

- cache key construction for TTS and non-TTS render artifacts
- render planning metadata and plan artifacts
- render preset selection, layout normalization, and readiness-adjacent estimates
- pure render progress stage payloads
- pure render geometry calculations for scaled positions, layout heights, and resize dimensions
- pure audio timeline calculations for WAV duration, timed segment metadata, concat-list contents, and FFmpeg command payloads
- pure video payload construction for speaker-slot/cast metadata, static overlay placement, dynamic frame composition, dialogue-card text layout, speaker palettes, generated-portrait layout, background normalization commands, dynamic overlay concat lists and commands, and final-video FFmpeg commands
- draft/render readiness estimates
- artifact metadata, TTS result metadata, debug-audio extraction metadata, line-timing summary, selected voice/profile summaries, and render result metadata envelope shaping
- render cache report summaries and final/intermediate/TTS-segment render cache transfer metadata shaping
- render diagnostics summaries and profile metadata payloads

Low-level FFmpeg execution stays in `backend/app/infra/ffmpeg/`. Phase 5 render micro-extraction is intentionally stopped: full video composition, audio mixdown execution, render cache materialization/stores, TTS synthesis orchestration, PIL drawing/saving, generated artifact writes, and final result file-stat assembly remain in `backend/app/services/rendering.py` until voice, media, and jobs ownership is clearer.

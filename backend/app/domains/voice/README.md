# Voice Domain

The voice domain owns TTS provider contracts, provider registry/capability selection helpers, provider capability/health metadata payload helpers, Docker-safe fallback provider behavior, voice profile metadata helpers, selected character recipe validation, provider artifact path/hash helpers, pure TTS cache-key payload helpers, provider failure/result metadata payload helpers, synthesis payloads, TTS synthesis orchestration, pure audio metadata helpers, pure Voice Lab preview provider-selection, manifest profile normalization, ephemeral profile payload decisions, and DB voice-profile-to-preview payload projection, voice datasets, and voice operation behavior as those pieces migrate out of legacy service modules.

This package is being introduced in small compatibility-first slices. Existing imports from `app.services.tts`, `app.services.voice_profiles`, `app.services.voice_replication`, `app.services.voice_preview_jobs`, `app.services.voice_operation_jobs`, and `app.services.character_voice_recipes` remain stable until each surface is safely moved.

Preview payload micro-extractions are intentionally stopped after the DB voice-profile payload projection. `LocalSpeechService` still owns profile resolution order, database lookups, provider availability checks, and preview/render handoff. Concrete OpenVoice, XTTS, and RVC provider bodies remain in `app.services.tts` until provider-specific move slices.

Runtime audio, uploaded references, previews, embeddings, datasets, recipes, and model checkpoints stay under configured runtime storage such as `backend/storage/voice_lab/` and `backend/storage/voice_models/`; they do not belong in source packages.

"""Voice profile metadata and path helpers."""

from app.domains.voice.profiles.artifacts import (
    reference_audio_content_hash_from_paths,
    sha256_path,
    voice_embedding_artifact_path,
    voice_embedding_artifact_path_for_reference,
)
from app.domains.voice.profiles.paths import (
    character_portrait_dir,
    voice_cache_dir,
    voice_embedding_dir,
    voice_lab_preview_dir,
    voice_models_dir,
    voice_reference_audio_dir,
    voice_reference_audio_profile_dir,
    voice_reference_chunk_dir,
)
from app.domains.voice.profiles.recipes import (
    CharacterVoiceRecipe,
    CharacterVoiceRecipeError,
    load_selected_character_recipe,
    selected_character_recipe_status,
    selected_recipe_path,
    validate_selected_character_recipe,
)

__all__ = [
    "CharacterVoiceRecipe",
    "CharacterVoiceRecipeError",
    "character_portrait_dir",
    "load_selected_character_recipe",
    "reference_audio_content_hash_from_paths",
    "selected_character_recipe_status",
    "selected_recipe_path",
    "sha256_path",
    "validate_selected_character_recipe",
    "voice_cache_dir",
    "voice_embedding_artifact_path",
    "voice_embedding_artifact_path_for_reference",
    "voice_embedding_dir",
    "voice_lab_preview_dir",
    "voice_models_dir",
    "voice_reference_audio_dir",
    "voice_reference_audio_profile_dir",
    "voice_reference_chunk_dir",
]

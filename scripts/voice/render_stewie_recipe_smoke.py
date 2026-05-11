from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.character_voice_recipes import CharacterVoiceRecipeError, validate_selected_character_recipe


DEFAULT_TEXT = "Blast, this voice render is finally using the proper selected recipe."
DEFAULT_OUTPUT = REPO_ROOT / "backend/storage/voice_models/stewie_griffin/previews/render_smoke/stewie_recipe_smoke.wav"


def synthesize(recipe, text: str, output_path: Path) -> None:
    from TTS.tts.configs.xtts_config import XttsConfig  # type: ignore
    from TTS.tts.models.xtts import Xtts  # type: ignore
    import torch  # type: ignore
    import torchaudio  # type: ignore

    output_path.parent.mkdir(parents=True, exist_ok=True)
    config = XttsConfig()
    config.load_json(str(recipe.config_path))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=str(recipe.checkpoint_dir), eval=True)
    model.to("cpu")
    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[str(path) for path in recipe.reference_wavs]
    )
    settings = dict(recipe.settings)
    inference_kwargs = {"temperature": float(settings.get("temperature", 0.7))}
    if settings.get("speed") is not None:
        inference_kwargs["speed"] = float(settings["speed"])
    signature = inspect.signature(model.inference)
    if "split_sentences" in signature.parameters and settings.get("split_sentences") is not None:
        inference_kwargs["split_sentences"] = bool(settings["split_sentences"])
    if "enable_text_splitting" in signature.parameters and settings.get("split_sentences") is not None:
        inference_kwargs["enable_text_splitting"] = bool(settings["split_sentences"])

    wav = model.inference(
        text,
        recipe.language,
        gpt_cond_latent,
        speaker_embedding,
        **inference_kwargs,
    )["wav"]
    torchaudio.save(str(output_path), torch.tensor(wav).unsqueeze(0), 24000)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Stewie Griffin XTTS smoke WAV from selected_recipe.json.")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    try:
        recipe = validate_selected_character_recipe("stewie_griffin")
    except CharacterVoiceRecipeError as exc:
        print(f"FAIL: {exc.code}: {exc.message}")
        if exc.details:
            print(f"Details: {exc.details}")
        return 1

    output_path = Path(args.out)
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path

    print(f"Provider: {recipe.provider}")
    print(f"Character: {recipe.character}")
    print(f"Checkpoint dir: {recipe.checkpoint_dir}")
    print(f"Reference WAV count: {len(recipe.reference_wavs)}")
    print(f"Language: {recipe.language}")
    print(f"Recipe settings: {recipe.settings}")
    print(f"Golden preview: {recipe.golden_preview_wav}")
    print(f"Output path: {output_path}")

    if args.validate_only:
        print("SUCCESS: selected_recipe.json validated.")
        return 0

    try:
        synthesize(recipe, args.text, output_path)
    except Exception as exc:
        print(f"FAIL: XTTS synthesis failed: {exc}")
        return 1

    print("SUCCESS: Stewie selected recipe rendered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

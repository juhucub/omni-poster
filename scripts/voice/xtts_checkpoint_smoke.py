import argparse
import glob
from pathlib import Path

import torch
import torchaudio
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint-dir", required=True)
    parser.add_argument("--refs", nargs="+", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    checkpoint_dir = Path(args.checkpoint_dir)
    config_path = checkpoint_dir / "config.json"

    if not config_path.exists():
        raise FileNotFoundError(f"Missing config.json: {config_path}")

    refs = []
    for pattern in args.refs:
        refs.extend(glob.glob(pattern))

    if not refs:
        raise FileNotFoundError("No reference WAVs matched --refs")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    device = "cpu"  # safest on Mac for now

    config = XttsConfig()
    config.load_json(str(config_path))

    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=str(checkpoint_dir), eval=True)
    model.to(device)

    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=refs
    )

    wav = model.inference(
        args.text,
        args.language,
        gpt_cond_latent,
        speaker_embedding,
        temperature=0.7,
    )["wav"]

    wav_tensor = torch.tensor(wav).unsqueeze(0)
    torchaudio.save(args.out, wav_tensor, 24000)

    print(f"Wrote: {args.out}")
    print(f"Checkpoint dir: {checkpoint_dir}")
    print(f"Reference WAVs: {len(refs)}")


if __name__ == "__main__":
    main()
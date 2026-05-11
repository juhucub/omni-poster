import argparse
import torch
from TTS.api import TTS

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--refs", nargs="+", required=True)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    device = "cpu"
    print(f"Using device: {device}")

    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

    tts.tts_to_file(
        text=args.text,
        speaker_wav=args.refs,
        language=args.language,
        file_path=args.out,
        split_sentences=True,
    )

    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
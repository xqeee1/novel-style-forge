#!/usr/bin/env python3
"""Extract an objective style fingerprint from a Chinese fiction text."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from style_utils import compute_profile, read_text


def main() -> None:
    ap = argparse.ArgumentParser(description="Measure the stylistic fingerprint of a fiction text.")
    ap.add_argument("--input", required=True, help="Plain-text file (.txt/.md) containing the sample")
    ap.add_argument("--out", required=True, help="Path to write the JSON style profile")
    ap.add_argument("--title", default="", help="Book title, stored in the profile")
    ap.add_argument("--author", default="", help="Author name, stored in the profile")
    ap.add_argument("--max-chars", type=int, default=500000, help="Cap on measured CJK characters")
    args = ap.parse_args()

    profile = compute_profile(read_text(args.input), args.title, args.author, args.max_chars)
    profile["meta"]["source_file"] = str(Path(args.input).resolve())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    m, s, v, n = profile["meta"], profile["syntax"], profile["vocabulary"], profile["narration"]
    print(f"OK: {m['chars']} CJK chars, {m['sentences']} sentences, {m['paragraphs']} paragraphs.")
    print(f"    avg sentence {s['avg_sentence_chars']} chars (std {s['std_sentence_chars']}), "
          f"short<=10 ratio {s['short_sentence_ratio_le10']}")
    print(f"    MATTR {v['mattr_1000']}, verb/adj/noun {v['verb_ratio']}/{v['adj_ratio']}/{v['noun_ratio']}")
    print(f"    dialogue ratio {n['dialogue_char_ratio']}, dominant person {n['dominant_person']}")
    print(f"    tokenizer={m['tokenizer']}  JSON -> {out.resolve()}")
    for w in profile["warnings"]:
        print(f"    WARNING: {w}")


if __name__ == "__main__":
    main()

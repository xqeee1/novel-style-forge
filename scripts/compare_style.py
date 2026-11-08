#!/usr/bin/env python3
"""Compare a draft against a saved style profile and emit actionable rewrite hints."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from style_utils import (
    METRIC_SPECS,
    compute_profile,
    content_word_sets,
    get_metric,
    read_text,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Score how closely a draft matches a style profile.")
    ap.add_argument("--profile", required=True, help="JSON file produced by analyze_style.py")
    ap.add_argument("--input", required=True, help="Draft text file to evaluate")
    ap.add_argument("--out", required=True, help="Path to write the JSON comparison report")
    ap.add_argument("--top", type=int, default=8, help="Number of deviations to surface")
    args = ap.parse_args()

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    draft = compute_profile(read_text(args.input))

    deviations = []
    weighted = 0.0
    weight_total = 0.0
    for path, label, weight, hint_low, hint_high in METRIC_SPECS:
        target = get_metric(profile, path)
        actual = get_metric(draft, path)
        denom = max(abs(target), abs(actual), 1e-6)
        severity = abs(target - actual) / denom
        similarity = max(0.0, 1.0 - severity)
        weighted += weight * similarity
        weight_total += weight
        if severity > 0.12:
            template = hint_low if actual < target else hint_high
            deviations.append({
                "metric": path,
                "label": label,
                "target": round(target, 4),
                "actual": round(actual, 4),
                "direction": "below" if actual < target else "above",
                "severity": round(severity, 3),
                "priority": round(severity * weight, 3),
                "hint": template.format(t=round(target, 2), a=round(actual, 2)),
            })
    deviations.sort(key=lambda d: d["priority"], reverse=True)
    overall = round(weighted / max(weight_total, 1e-6), 4)
    grade = "high" if overall >= 0.82 else ("medium" if overall >= 0.68 else "low")

    target_set, _ = content_word_sets(profile, 40)
    draft_set, _ = content_word_sets(draft, 40)
    union = target_set | draft_set
    shared = sorted(target_set & draft_set)
    jaccard = round(len(shared) / len(union), 4) if union else 0.0
    coverage = round(len(shared) / len(target_set), 4) if target_set else 0.0
    overlap_note = (
        "High lexical overlap: check that the draft reuses techniques rather than the source's pet words."
        if coverage > 0.55 else
        "Low lexical overlap is expected and healthy: style lives in rhythm and technique, not in copied vocabulary."
    )

    top = deviations[: max(args.top, 1)]
    report = {
        "target": {
            "title": profile.get("meta", {}).get("title", ""),
            "author": profile.get("meta", {}).get("author", ""),
            "chars": profile.get("meta", {}).get("chars", 0),
        },
        "draft": {
            "chars": draft["meta"]["chars"],
            "sentences": draft["meta"]["sentences"],
            "tokenizer": draft["meta"]["tokenizer"],
        },
        "overall_similarity": overall,
        "grade": grade,
        "metrics_compared": len(METRIC_SPECS),
        "deviation_count": len(deviations),
        "word_overlap": {
            "jaccard": jaccard,
            "target_word_coverage": coverage,
            "shared_words": shared[:20],
            "note": overlap_note,
        },
        "top_deviations": top,
        "next_actions": [d["hint"] for d in top],
        "caveats": [
            "Similarity measures surface style only; it does not judge plot, character voice or coherence.",
            "Short drafts are noisy: metrics stabilise above roughly 1500 Chinese characters.",
            "Do not optimise by copying the source's high-frequency words; fix rhythm and technique first.",
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: similarity {overall} ({grade}), {len(deviations)} deviations, top {len(top)} surfaced.")
    print(f"    word overlap jaccard={jaccard} coverage={coverage}")
    print(f"    JSON -> {out.resolve()}")
    for d in top:
        print(f"    - {d['label']}: target {d['target']} vs draft {d['actual']} ({d['direction']})")
    for w in draft["warnings"]:
        print(f"    DRAFT WARNING: {w}")


if __name__ == "__main__":
    main()

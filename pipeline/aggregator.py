"""
pipeline/aggregator.py — Aggregates evaluation results into a summary report.
Computes average scores, good/bad distribution, per-sub-score averages,
and (optionally) improvement delta between two sets of results.
"""
import json
import os


def compute_summary(results: list[dict]) -> dict:
    """Compute aggregate metrics from a list of CallEvaluation dicts."""
    if not results:
        return {}

    scores = [r["score"] for r in results]
    good = [r for r in results if r["verdict"] == "good"]
    bad  = [r for r in results if r["verdict"] == "bad"]

    # Sub-score averages (only where sub_scores field exists)
    sub_keys = ["empathy_score", "tone_score", "clarity_score",
                "negotiation_score", "compliance_score", "repetition_penalty"]
    sub_avgs = {}
    for k in sub_keys:
        vals = [r["sub_scores"][k] for r in results if "sub_scores" in r]
        sub_avgs[k] = round(sum(vals) / len(vals), 2) if vals else None

    # Binary signal rates
    binary_keys = ["acknowledged_user_emotion", "offered_payment_solution",
                   "repeated_phrases", "escalation_handled_properly"]
    binary_rates = {}
    for k in binary_keys:
        vals = [r["binary_signals"][k] for r in results if "binary_signals" in r]
        binary_rates[k] = round(sum(vals) / len(vals) * 100, 1) if vals else None  # as %

    return {
        "total_calls": len(results),
        "avg_score": round(sum(scores) / len(scores), 2),
        "min_score": min(scores),
        "max_score": max(scores),
        "good_count": len(good),
        "bad_count": len(bad),
        "good_pct": round(len(good) / len(results) * 100, 1),
        "per_call": [{"call_id": r["call_id"], "score": r["score"], "verdict": r["verdict"]} for r in results],
        "sub_score_averages": sub_avgs,
        "binary_signal_rates_pct": binary_rates,
    }





def save_summary(summary: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary saved to {path}")

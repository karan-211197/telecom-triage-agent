import json
import os
import sys
import time
from collections import defaultdict

DATA = sys.argv[1] if len(sys.argv) > 1 else "data/scenarios.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "results/eval_results.json"

EXTRA = sys.argv[3:]
USE_SPECS = "nospecs" not in EXTRA
USE_GRAPH = "graph" in EXTRA

if USE_GRAPH:
    from agent_graph import run_agent_graph as run_agent
else:
    from agent import run_agent


def main():
    with open(DATA) as f:
        scenarios = json.load(f)

    rows = []
    for s in scenarios:
        truth = s["ground_truth"]["root_cause"]
        start = time.time()
        try:
            result = run_agent(s, use_specs=USE_SPECS)
        except Exception as e:
            result = {
                "status": "error",
                "diagnosis": None,
                "steps": 0,
                "tool_calls": 0,
                "trace": [],
                "forced": False,
                "error": f"{type(e).__name__}: {e}",  # NEW: include the exception type
            }
        seconds = round(time.time() - start, 1)

        predicted = result["diagnosis"].root_cause if result["diagnosis"] else None
        correct = predicted == truth
        rows.append({
            "id": s["id"],
            "truth": truth,
            "predicted": predicted,
            "correct": correct,
            "ambiguous": s["ambiguous"],
            "status": result["status"],
            "steps": result["steps"],
            "tool_calls": result["tool_calls"],
            "seconds": seconds,
            "forced": result["forced"],
            "used_specs": any(t["tool"] == "ask_specs" for t in result["trace"]),
            "trace": result["trace"],
            "error": result.get("error"),  # NEW
        })
        flag = "OK  " if correct else "FAIL"
        print(f"{s['id']} {flag} truth={truth:<17} predicted={str(predicted):<17} calls={result['tool_calls']} {seconds}s")

    total = len(rows)
    n_correct = sum(r["correct"] for r in rows)
    clear = [r for r in rows if not r["ambiguous"]]
    amb = [r for r in rows if r["ambiguous"]]

    print("\n=== SUMMARY ===")
    print(f"Engine: {'langgraph' if USE_GRAPH else 'raw loop'} | ask_specs {'on' if USE_SPECS else 'off'}")
    print(f"Overall accuracy:   {n_correct}/{total} ({100 * n_correct / total:.0f}%)")
    print(f"Clear scenarios:    {sum(r['correct'] for r in clear)}/{len(clear)}")
    print(f"Ambiguous scenarios: {sum(r['correct'] for r in amb)}/{len(amb)}")
    print(f"Avg tool calls per task: {sum(r['tool_calls'] for r in rows) / total:.1f}")
    print(f"Avg steps per task:      {sum(r['steps'] for r in rows) / total:.1f}")
    print(f"Avg seconds per task:    {sum(r['seconds'] for r in rows) / total:.1f}")
    print(f"Hit step limit: {sum(r['status'] == 'max_steps' for r in rows)}")
    print(f"Errors:         {sum(r['status'] == 'error' for r in rows)}")
    print(f"Answers forced at last step: {sum(r['forced'] for r in rows)}")
    print(f"Tasks that called ask_specs: {sum(r['used_specs'] for r in rows)}")

    by_cause = defaultdict(lambda: [0, 0])
    for r in rows:
        by_cause[r["truth"]][1] += 1
        by_cause[r["truth"]][0] += r["correct"]
    print("\nAccuracy by root cause:")
    for cause, (ok, n) in by_cause.items():
        print(f"  {cause:<18} {ok}/{n}")

    failures = [r for r in rows if not r["correct"]]
    print(f"\n=== FAILURE ANALYSIS ({len(failures)}) ===")
    for r in failures:
        print(f"\n{r['id']}: truth={r['truth']} predicted={r['predicted']} status={r['status']} ambiguous={r['ambiguous']}")
        if r["status"] == "error":  # NEW
            print("   error:", r["error"])  # NEW
        for t in r["trace"]:
            print("   ->", t["tool"], t["args"])

    os.makedirs("results", exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"accuracy": n_correct / total, "rows": rows}, f, indent=2)
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
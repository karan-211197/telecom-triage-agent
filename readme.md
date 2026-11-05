# Telecom Fault-Triage Agent

An LLM agent that diagnoses 5G handover problems. Given a symptom for a cell, it
investigates with tools (KPI lookup, log search, optional 3GPP spec lookup), then
returns a validated, structured diagnosis: root cause, evidence, recommended fix
and confidence.

All data is synthetic. No operator or employer data is used.

## Results

| Run | Scenarios | Accuracy | Notes |
|---|---|---|---|
| v1 baseline | 30 (dev) | 23/30 (77%) | All 7 failures were step-limit exhaustions, none were wrong answers |
| v2 after fixes | 30 (dev) | 30/30 | Tuned on this set, so treat as optimistic |
| v2 held-out, repeated runs | 60 (new seed) | **56-58/60 (93-97%)** | 5 runs across tool configurations |

Held-out detail: clear scenarios 48/48 in every run; ambiguous scenarios 8-10 of 12.
About 4 tool calls, 4 steps and 10 s per task.

Identical configurations varied by up to 2 scenarios between runs, so differences
of 1-2 scenarios are treated as noise.

### Spec-lookup ablation
`ask_specs` (calls a separately deployed RAG service over TS 38.300) was added as a
third tool. With the tool and a prompt hint it was called in 0 of 60 tasks, and
accuracy (56/60) was within noise of the tool-off run (58/60). The synthetic faults
are diagnosable from KPIs and logs, and TS 38.300 does not cover timer-level
details, so the tool added no measurable value here.

## How it works

    symptom -> agent loop (LLM + tools, max 10 steps)
                 |- get_kpi(cell_id)
                 |- search_logs(keyword)
                 |- ask_specs(question)     -> HTTP call to a RAG service (optional)
                 '- submit_diagnosis(...)   -> validated by Pydantic -> result

- Tool-calling loop written from scratch, with a step limit, a duplicate-call guard
  and a forced final answer on the last step.
- The final answer is a tool call validated against a Pydantic schema. Invalid
  answers are returned to the model to fix.
- Six fault classes: coverage_edge, missing_neighbor, late_trigger,
  target_overload, xn_transport, ul_power_control.
- Seeded scenario generator with KPIs, logs, noise lines and red-herring log lines
  in "ambiguous" scenarios. The agent never sees the ground truth.

## What the evaluation found

- v1 never gave a wrong answer but ran out of steps on 7 of 30 scenarios. The agent
  kept probing cells that did not exist. Fixes: a stopping rule in the prompt, a
  clearer tool error, a duplicate-call guard and a forced final step.
- On held-out data, every failure was an ambiguous scenario with misleading log
  lines. Two scenarios failed in all five runs.
- Most failures share one pattern: the agent diagnosed target_overload from a log
  line claiming the target was overloaded, without checking that cell's KPIs.
- The agent's confidence was "high" on every wrong answer, so it is not a reliable
  signal.

## Limitations

- Synthetic, templated data from one generator. Held-out scenarios share its
  distribution, so real-world accuracy would be lower.
- Small samples (60 scenarios, 12 ambiguous). The held-out set was re-run several
  times for ablations, with no prompt changes made to fix its failures.
- Scoring is exact match on root cause only. The recommended fix is not graded.
- Tool outputs are not stored in the trace, which limits failure analysis.

## Run it

    pip install -r requirements.txt
    # .env: OPENAI_API_KEY=...   (optional: P1_URL, P1_API_KEY for ask_specs)
    python data/generate_scenarios.py
    python agent.py
    python -m tests.evaluate
    python -m tests.evaluate data/heldout.json results/out.json nospecs

## Next

- Verify claims in logs against the cited cell's KPIs before concluding.
- Index the RRC spec (TS 38.331) so the spec tool can answer timer questions.
- Rebuild the agent in LangGraph and compare on the same held-out set.
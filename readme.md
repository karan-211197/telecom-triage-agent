# Telecom Fault-Triage Agent

An LLM agent that diagnoses 5G handover problems. Given a symptom for a cell, it
investigates with tools (KPI lookup, log search, optional 3GPP spec lookup), then
returns a validated, structured diagnosis: root cause, evidence, recommended fix
and confidence. Implemented twice: a hand-written tool-calling loop and a
LangGraph version, evaluated on the same scenarios.

All data is synthetic. No operator or employer data is used.

## Results

| Run | Scenarios | Accuracy | Notes |
|---|---|---|---|
| v1 baseline (raw loop) | 30 (dev) | 23/30 (77%) | All 7 failures were step-limit exhaustions, none were wrong answers |
| v2 after fixes (raw loop) | 30 (dev) | 30/30 | Tuned on this set, so treat as optimistic |
| v2 held-out, raw loop | 60 (new seed) | **56-58/60 (93-97%)** | 5 runs across tool configurations |
| v2 held-out, LangGraph | 60 (new seed) | **55/60 (92%)** | Same prompt, tools and model calls |

Held-out detail: clear scenarios 48/48 in every run; ambiguous scenarios 7-10 of 12.
About 4 tool calls, 4 steps and 10 s per task for both engines.

Identical configurations varied by up to 2-3 scenarios between runs, so differences
of that size are treated as noise. One earlier LangGraph run was discarded because
API calls started failing partway through (it had 32/32 correct before the failures).

### Spec-lookup ablation
`ask_specs` (calls a separately deployed RAG service over TS 38.300) was added as a
third tool. With the tool and a prompt hint it was called in 0 of 60 tasks, and
accuracy (56/60) was within noise of the tool-off run (58/60). The synthetic faults
are diagnosable from KPIs and logs, and TS 38.300 does not cover timer-level
details, so the tool added no measurable value here.

### Raw loop vs LangGraph
LangGraph is used for orchestration only: the model and tools nodes call the same
OpenAI client and tool code as the raw loop, with the same prompt, step limit,
duplicate-call guard, forced final answer and Pydantic validation. Accuracy, tool
calls and latency were comparable. LangGraph did not improve accuracy here; its
benefit is explicit state and routing that make extensions (human approval,
checkpointing) straightforward.

## How it works

    symptom -> loop or graph (LLM + tools, max 10 steps)
                 |- get_kpi(cell_id)
                 |- search_logs(keyword)
                 |- ask_specs(question)     -> HTTP call to a RAG service (optional)
                 '- submit_diagnosis(...)   -> validated by Pydantic -> result

- `agent.py`: tool-calling loop written from scratch.
- `agent_graph.py`: the same agent as a LangGraph StateGraph (model node, tools
  node, conditional edges for tool routing and the step limit).
- Step limit, duplicate-call guard and a forced final answer on the last step.
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
  lines. Two scenarios failed in every run of both engines.
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
    python agent.py                      # raw loop, one scenario
    python agent_graph.py                # LangGraph, one scenario
    python -m tests.evaluate             # raw loop, dev set
    python -m tests.evaluate data/heldout.json results/out.json nospecs graph

## Next

- Verify claims in logs against the cited cell's KPIs before concluding.
- Index the RRC spec (TS 38.331) so the spec tool can answer timer questions.
- Add a human-approval step before a fix is recommended (a natural LangGraph
  extension).
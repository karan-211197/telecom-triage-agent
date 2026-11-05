from dotenv import load_dotenv
load_dotenv()

import json
from openai import OpenAI
from pydantic import ValidationError

from schemas import Diagnosis
from tools.triage_tools import TriageTools, TOOL_SPECS

client = OpenAI()
MODEL = "gpt-4o-mini"
MAX_STEPS = 10

SYSTEM_PROMPT = """You are a senior 5G RAN fault-triage engineer. You receive a symptom for a serving cell and must find the root cause using the tools.

Healthy reference values: handover execution and preparation success above 98%, RLF below about 5 per hour, DL RSRP better than -95 dBm, DL SINR above 10 dB, UL SINR above 8 dB, PUSCH BLER below 10%, DL PRB utilization below 80%, power headroom positive.

Known fault catalogue (choose exactly one):
- coverage_edge: poor radio coverage at the cell edge
- missing_neighbor: the handover target is missing from the neighbor relation table
- late_trigger: handover trigger parameters (A3 offset / time-to-trigger) are too conservative, so the link fails before handover
- target_overload: the target cell has no radio resources to admit handovers
- xn_transport: the Xn / transport path between gNBs is failing
- ul_power_control: uplink power control is misconfigured, so UEs are power limited

How to work:
1. Check the serving cell's KPIs and search the logs (ERROR and WARN first).
2. Only the serving cell and cells named in the logs have data. If a log line names a target or neighbor cell, check that cell's KPIs. If the logs name no other cell, the fault is on the serving cell itself, so diagnose from its KPIs and logs. Never guess cell names.
3. Do not conclude from a single signal. Confirm with at least two independent pieces of evidence from the data you have, and watch for misleading log lines.
4. Do not repeat a call you already made. Once you have two supporting pieces of evidence, call submit_diagnosis once, citing the KPI values and log lines you actually observed."""

SPECS_LINE = "\n5. If you are unsure what a procedure, timer or event means (for example T310, A3 or Xn), you may call ask_specs. It returns 3GPP background, not incident data."

SUBMIT_SPEC = {
    "type": "function",
    "function": {
        "name": "submit_diagnosis",
        "description": "Submit your final diagnosis. Call this once, when you have enough evidence.",
        "parameters": Diagnosis.model_json_schema(),
    },
}

FORCE_SUBMIT = {"type": "function", "function": {"name": "submit_diagnosis"}}


def tool_msg(call_id, payload):
    return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(payload)}


def run_agent(scenario, max_steps=MAX_STEPS, use_specs=True):
    tools = TriageTools(scenario)
    system_prompt = SYSTEM_PROMPT + (SPECS_LINE if use_specs else "")
    tool_specs = TOOL_SPECS if use_specs else [
        t for t in TOOL_SPECS if t["function"]["name"] != "ask_specs"
    ]
    messages = [
        {"role": "system", "content": system_prompt},  # FIX: was SYSTEM_PROMPT
        {"role": "user", "content": scenario["symptom"]},
    ]
    trace = []
    seen = set()

    for step in range(max_steps):
        is_last = step == max_steps - 1
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tool_specs + [SUBMIT_SPEC],  # FIX: was TOOL_SPECS
            tool_choice=FORCE_SUBMIT if is_last else "auto",
            temperature=0,
        )
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            messages.append({
                "role": "user",
                "content": "Use the tools to investigate, then call submit_diagnosis.",
            })
            continue

        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                messages.append(tool_msg(call.id, {"error": "Arguments were not valid JSON"}))
                continue
            trace.append({"tool": name, "args": args})

            if name == "submit_diagnosis":
                try:
                    diagnosis = Diagnosis.model_validate(args)
                except ValidationError as e:
                    messages.append(tool_msg(call.id, {"error": str(e)}))
                    continue
                return {
                    "status": "ok",
                    "diagnosis": diagnosis,
                    "steps": step + 1,
                    "tool_calls": tools.calls,
                    "trace": trace,
                    "forced": is_last,
                }

            key = (name, json.dumps(args, sort_keys=True))
            if key in seen:
                messages.append(tool_msg(call.id, {
                    "error": "You already made this exact call and the result has not changed. Use the evidence you have, or try a different call."
                }))
                continue
            seen.add(key)

            result = tools.run(name, args)
            messages.append(tool_msg(call.id, result))

    return {
        "status": "max_steps",
        "diagnosis": None,
        "steps": max_steps,
        "tool_calls": tools.calls,
        "trace": trace,
        "forced": False,
    }


if __name__ == "__main__":
    with open("data/scenarios.json") as f:
        scenarios = json.load(f)
    scenario = scenarios[0]

    result = run_agent(scenario)
    print("Symptom:", scenario["symptom"])
    print("Status:", result["status"], "| steps:", result["steps"], "| tool calls:", result["tool_calls"])
    for t in result["trace"]:
        print("  ->", t["tool"], t["args"])
    if result["diagnosis"]:
        print(result["diagnosis"].model_dump_json(indent=2))
    print("Ground truth:", scenario["ground_truth"]["root_cause"])
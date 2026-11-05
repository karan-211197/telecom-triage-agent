import json
import operator
from typing import Annotated, Any
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from pydantic import ValidationError

from agent import (
    client, MODEL, MAX_STEPS, SYSTEM_PROMPT, SPECS_LINE,
    SUBMIT_SPEC, FORCE_SUBMIT, tool_msg,
)
from schemas import Diagnosis
from tools.triage_tools import TriageTools, TOOL_SPECS


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    trace: Annotated[list, operator.add]
    seen: list
    calls: list
    step: int
    pending_calls: bool
    diagnosis: Any
    forced: bool


def build_graph(tools, max_steps, tool_specs):
    def call_model(state):
        step = state["step"]
        is_last = step == max_steps - 1
        resp = client.chat.completions.create(
            model=MODEL,
            messages=state["messages"],
            tools=tool_specs + [SUBMIT_SPEC],
            tool_choice=FORCE_SUBMIT if is_last else "auto",
            temperature=0,
        )
        msg = resp.choices[0].message
        update = {
            "messages": [msg],
            "calls": list(msg.tool_calls or []),
            "step": step + 1,
            "pending_calls": bool(msg.tool_calls),
            "forced": is_last,
        }
        if not msg.tool_calls:
            update["messages"].append({
                "role": "user",
                "content": "Use the tools to investigate, then call submit_diagnosis.",
            })
        return update

    def run_tools(state):
        new_messages, new_trace = [], []
        seen = list(state["seen"])
        diagnosis = None

        for call in state["calls"]:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                new_messages.append(tool_msg(call.id, {"error": "Arguments were not valid JSON"}))
                continue
            new_trace.append({"tool": name, "args": args})

            if name == "submit_diagnosis":
                try:
                    diagnosis = Diagnosis.model_validate(args)
                except ValidationError as e:
                    new_messages.append(tool_msg(call.id, {"error": str(e)}))
                    continue
                new_messages.append(tool_msg(call.id, {"status": "received"}))
                break

            key = f"{name}:{json.dumps(args, sort_keys=True)}"
            if key in seen:
                new_messages.append(tool_msg(call.id, {
                    "error": "You already made this exact call and the result has not changed. Use the evidence you have, or try a different call."
                }))
                continue
            seen.append(key)
            new_messages.append(tool_msg(call.id, tools.run(name, args)))

        return {
            "messages": new_messages,
            "trace": new_trace,
            "seen": seen,
            "diagnosis": diagnosis,
        }

    def after_model(state):
        if state["pending_calls"]:
            return "tools"
        return END if state["step"] >= max_steps else "model"

    def after_tools(state):
        if state["diagnosis"] is not None or state["step"] >= max_steps:
            return END
        return "model"

    builder = StateGraph(AgentState)
    builder.add_node("model", call_model)
    builder.add_node("tools", run_tools)
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", after_model, {"tools": "tools", "model": "model", END: END})
    builder.add_conditional_edges("tools", after_tools, {"model": "model", END: END})
    return builder.compile()


def run_agent_graph(scenario, max_steps=MAX_STEPS, use_specs=True):
    tools = TriageTools(scenario)
    system_prompt = SYSTEM_PROMPT + (SPECS_LINE if use_specs else "")
    tool_specs = TOOL_SPECS if use_specs else [
        t for t in TOOL_SPECS if t["function"]["name"] != "ask_specs"
    ]
    graph = build_graph(tools, max_steps, tool_specs)

    initial = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": scenario["symptom"]},
        ],
        "trace": [],
        "seen": [],
        "calls": [],
        "step": 0,
        "pending_calls": False,
        "diagnosis": None,
        "forced": False,
    }
    final = graph.invoke(initial, config={"recursion_limit": 60})

    diagnosis = final["diagnosis"]
    return {
        "status": "ok" if diagnosis is not None else "max_steps",
        "diagnosis": diagnosis,
        "steps": final["step"],
        "tool_calls": tools.calls,
        "trace": final["trace"],
        "forced": diagnosis is not None and final["forced"],
    }


if __name__ == "__main__":
    with open("data/scenarios.json") as f:
        scenarios = json.load(f)
    scenario = scenarios[0]

    result = run_agent_graph(scenario)
    print("Symptom:", scenario["symptom"])
    print("Status:", result["status"], "| steps:", result["steps"], "| tool calls:", result["tool_calls"])
    for t in result["trace"]:
        print("  ->", t["tool"], t["args"])
    if result["diagnosis"]:
        print(result["diagnosis"].model_dump_json(indent=2))
    print("Ground truth:", scenario["ground_truth"]["root_cause"])
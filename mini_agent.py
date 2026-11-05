from dotenv import load_dotenv
load_dotenv()

import json
from openai import OpenAI

client = OpenAI()


def get_cell_kpi(cell_id: str) -> dict:
    data = {
        "cell_1": {"ho_success_rate": 82.5, "rsrp_avg_dbm": -104},
        "cell_2": {"ho_success_rate": 99.1, "rsrp_avg_dbm": -88},
    }
    return data.get(cell_id, {"error": "unknown cell"})


TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_cell_kpi",
        "description": "Get handover success rate and average RSRP for a cell.",
        "parameters": {
            "type": "object",
            "properties": {"cell_id": {"type": "string"}},
            "required": ["cell_id"],
        },
    },
}]

REGISTRY = {"get_cell_kpi": get_cell_kpi}


def run_agent(question: str, max_steps: int = 5) -> str:
    messages = [
        {"role": "system", "content": "You are a 5G RAN fault triage assistant. Use tools to get facts before answering."},
        {"role": "user", "content": question},
    ]
    for step in range(max_steps):
        resp = client.chat.completions.create(
            model="gpt-4o-mini", messages=messages, tools=TOOLS
        )
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            return msg.content

        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            print(f"step {step}: calling {call.function.name} with {args}")
            result = REGISTRY[call.function.name](**args)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),
            })

    return "Stopped: step limit reached"


if __name__ == "__main__":
    print(run_agent("Is cell_1 healthy?"))
import json
from tools.triage_tools import TriageTools

with open("data/scenarios.json") as f:
    scenarios = json.load(f)

scenario = scenarios[0]
tools = TriageTools(scenario)

print("Symptom:", scenario["symptom"])
print(tools.run("get_kpi", {"cell_id": scenario["serving_cell"]}))
print(tools.run("search_logs", {"keyword": "ERROR"}))
print(tools.run("get_kpi", {"cell_id": "cell_99"}))
print(tools.run("fake_tool", {}))
print("calls:", tools.calls)
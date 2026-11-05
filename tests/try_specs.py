from tools.triage_tools import TriageTools

tools = TriageTools({"kpis": {}, "logs": []})
print(tools.run("ask_specs", {"question": "What happens when radio link failure is declared?"}))
import os

import requests
from dotenv import load_dotenv

load_dotenv()


class TriageTools:
    def __init__(self, scenario):
        self.kpis = scenario["kpis"]
        self.logs = scenario["logs"]
        self.calls = 0

    def get_kpi(self, cell_id):
        if cell_id not in self.kpis:
            return {"error": f"No KPI data for {cell_id}. KPI data exists only for the serving cell and cells named in the logs. Do not guess cell names."}
        return self.kpis[cell_id]

    def search_logs(self, keyword, max_results=10):
        keyword = keyword.lower()
        hits = [line for line in self.logs if keyword in line.lower()]
        return {"match_count": len(hits), "lines": hits[:max_results]}

    def ask_specs(self, question):
        base_url = os.getenv("P1_URL")
        if not base_url:
            return {"error": "Spec lookup is not configured"}
        headers = {"X-API-Key": os.getenv("P1_API_KEY", "")}
        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/ask",
                json={"question": question, "k": 3},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            return {"error": f"Spec lookup failed (HTTP {e.response.status_code})"}
        except requests.RequestException as e:
            return {"error": f"Spec lookup failed ({type(e).__name__})"}
        data = resp.json()
        return {"answer": data.get("answer", ""), "sources": data.get("sources", [])}

    def run(self, name, args):
        self.calls += 1
        methods = {
            "get_kpi": self.get_kpi,
            "search_logs": self.search_logs,
            "ask_specs": self.ask_specs,
        }
        if name not in methods:
            return {"error": f"Unknown tool: {name}"}
        try:
            return methods[name](**args)
        except TypeError as e:
            return {"error": f"Bad arguments for {name}: {e}"}


TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_kpi",
            "description": (
                "Get KPIs for one cell: handover execution and preparation success rates, "
                "RLF per hour, DL RSRP and SINR, UL SINR, PUSCH BLER, power headroom and "
                "DL PRB utilization. Works for the serving cell and for target or neighbor cells."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cell_id": {"type": "string", "description": "Cell name, e.g. cell_7"}
                },
                "required": ["cell_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": (
                "Search the RAN logs for a keyword (case-insensitive substring match). "
                "Try terms like ERROR, WARN, RLF, PCI, timeout, SCTP, or a cell name. "
                "Returns the match count and up to 10 matching lines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Text to search for"}
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_specs",
            "description": (
                "Look up 3GPP specification text (currently TS 38.300, the NR overall "
                "description) for definitions and procedure details, for example how handover, "
                "radio link failure or conditional handover work. Returns a short answer with "
                "clause and page citations. It contains no data about this incident, so use it "
                "for background knowledge only, never for facts about the cells."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "A specific question about a 5G NR procedure or concept"}
                },
                "required": ["question"],
            },
        },
    },
]
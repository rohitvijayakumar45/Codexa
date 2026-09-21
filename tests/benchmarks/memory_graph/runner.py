import json
import os
import time
import sys
from typing import Any
import threading
from pathlib import Path
from dotenv import load_dotenv

# Load env before any backend imports
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

# Adjust path so we can import from backend
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.agents.jobs import JobManager
from backend.agents.llm import LLMClient
from backend.graph.service import GraphService
from backend.memory.store import MemoryStore
import backend.agents.tools as agent_tools

BENCHMARK_DIR = Path(__file__).parent
# Per-run output dir so different models/campaigns don't overwrite each other's files.
RAW_RUNS_DIR = BENCHMARK_DIR / os.getenv("BENCHMARK_RUN_DIR", "raw_runs")
RAW_RUNS_DIR.mkdir(exist_ok=True)

QUESTIONS_PATH = BENCHMARK_DIR / "questions.json"
CONFIGS_PATH = BENCHMARK_DIR / "configs.json"

MODEL = os.getenv("BENCHMARK_MODEL", "tokenrouter/z-ai/glm-5.3-free")
REPOSITORY = os.getenv("BENCHMARK_REPO", "Exam-Proctoring")
# Deeper-run controls (all optional, backwards-compatible defaults):
#   BENCHMARK_REPS       — repetitions per (mode, question) for mean +/- CI (default 1)
#   BENCHMARK_MODES      — comma list of config ids to run (default: all in configs.json)
#   BENCHMARK_QUESTIONS  — comma list of question ids to run (default: all)
REPS = int(os.getenv("BENCHMARK_REPS", "1") or 1)
_MODES_FILTER = [m.strip() for m in os.getenv("BENCHMARK_MODES", "").split(",") if m.strip()]
_Q_FILTER = [q.strip() for q in os.getenv("BENCHMARK_QUESTIONS", "").split(",") if q.strip()]

def load_json(p: Path) -> dict:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

questions = load_json(QUESTIONS_PATH)
configs = load_json(CONFIGS_PATH)

original_tools_for_groups = agent_tools.tools_for_groups
original_execute = agent_tools.execute_tool
current_allowed_tools = set()
current_tool_counts = {}

def benchmark_tools_for_groups(groups: list[str]) -> list[dict]:
    tools = original_tools_for_groups(groups)
    return [t for t in tools if t['function']['name'] in current_allowed_tools]

def benchmark_execute(name: str, args: dict, repository: str, **kwargs) -> str:
    if name not in current_allowed_tools:
        return f"Tool {name} is explicitly disabled in this benchmark mode."
    global current_tool_counts
    current_tool_counts[name] = current_tool_counts.get(name, 0) + 1
    return original_execute(name, args, repository, **kwargs)

original_stream = LLMClient.stream
def benchmark_stream(self, *args, **kwargs):
    # Enforce a 90 second network timeout per LLM call to prevent hanging
    kwargs["timeout"] = 90
    return original_stream(self, *args, **kwargs)

original_complete = LLMClient.complete
def benchmark_complete(self, *args, **kwargs):
    kwargs["timeout"] = 90
    return original_complete(self, *args, **kwargs)

# Monkey-patch correctly across all modules that might have imported them directly
import backend.agents.jobs as jobs
import backend.agents.planner as planner
import backend.agents.controller as controller

# If they imported the module, this patches the module
agent_tools.tools_for_groups = benchmark_tools_for_groups
agent_tools.execute_tool = benchmark_execute

# If they did `from tools import execute_tool`, we must patch their local namespace
if hasattr(jobs, 'execute_tool'): jobs.execute_tool = benchmark_execute
if hasattr(controller, 'execute_tool'): controller.execute_tool = benchmark_execute
if hasattr(planner, 'tools_for_groups'): planner.tools_for_groups = benchmark_tools_for_groups

LLMClient.stream = benchmark_stream
LLMClient.complete = benchmark_complete

from backend.graph.repository import InMemoryGraphRepository
from backend.graph.events import InMemoryGraphEventWriter
from backend.repository.api import reindex_repository

def run_benchmark():
    global current_allowed_tools, current_tool_counts

    active_questions = [q for q in questions if not _Q_FILTER or q["id"] in _Q_FILTER]
    for config_id, config in configs.items():
        if _MODES_FILTER and config_id not in _MODES_FILTER:
            continue
        print(f"\n{'='*50}\nSTARTING MODE: {config['name']} (reps={REPS}, model={MODEL})\n{'='*50}", flush=True)
        current_allowed_tools = set(config["allowed_tools"])
        
        graph_svc = None
        if config["enable_graph"]:
            graph_svc = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
            
        store_svc = MemoryStore() if config["enable_memory"] else None

        # Reindex if graph is enabled so the InMemoryGraphRepository isn't empty
        if graph_svc is not None:
            print("Reindexing repository into in-memory graph (structural only)...", flush=True)
            reindex_repository(REPOSITORY, store=store_svc or MemoryStore(), graph=graph_svc, llm=None)
            print("Reindex complete.", flush=True)

        for q in active_questions:
            for rep in range(REPS):
                print(f"\nRunning Q: {q['id']} | Mode: {config_id} | rep {rep + 1}/{REPS}")
                current_tool_counts = {}

                client = LLMClient()
                jm = JobManager(llm=client, graph=graph_svc, store=store_svc)

                job = jm.create(
                    repository=REPOSITORY,
                    model=MODEL,
                    messages=[{"role": "user", "content": q["text"]}]
                )

                start_time = time.time()
                jm.start(job, last_user_text=q["text"])

                while job.status in ("running", "queued"):
                    time.sleep(1)
                end_time = time.time()
                time.sleep(2)

                duration = end_time - start_time
                in_tok = getattr(job, "prompt_tokens", 0)
                out_tok = getattr(job, "completion_tokens", 0)

                # The real answer is the last ASSISTANT message carrying substantive prose — NOT
                # job.messages[-1], which is usually a trailing tool result (a disabled-tool notice
                # or a 404). Capturing the wrong message made real answers look like 60-char stubs.
                answer = ""
                for m in reversed(job.messages or []):
                    if m.get("role") == "assistant":
                        c = m.get("content")
                        if isinstance(c, str) and c.strip():
                            answer = c
                            break

                metrics = {
                    "question_id": q["id"],
                    "mode": config_id,
                    "mode_name": config["name"],
                    "model": MODEL,
                    "rep": rep,
                    "status": job.status,
                    "duration_seconds": duration,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "total_tokens": in_tok + out_tok,
                    "tool_calls_total": sum(current_tool_counts.values()),
                    "tool_counts": current_tool_counts.copy(),
                    "job_id": job.id,
                    "answer": answer,
                    "answer_chars": len(answer),
                }

                out_file = RAW_RUNS_DIR / f"{config_id}_{q['id']}_r{rep}.json"
                with out_file.open("w", encoding="utf-8") as f:
                    json.dump(metrics, f, indent=2)

                print(f"Finished {q['id']} r{rep}. Status: {job.status}. "
                      f"In:{in_tok} Out:{out_tok} Tot:{metrics['total_tokens']} "
                      f"Tools:{metrics['tool_calls_total']} Time:{duration:.1f}s")

if __name__ == "__main__":
    run_benchmark()

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
RAW_RUNS_DIR = BENCHMARK_DIR / "raw_runs"
RAW_RUNS_DIR.mkdir(exist_ok=True)

QUESTIONS_PATH = BENCHMARK_DIR / "questions.json"
CONFIGS_PATH = BENCHMARK_DIR / "configs.json"

MODEL = os.getenv("BENCHMARK_MODEL", "tokenrouter/z-ai/glm-5.3-free")
REPOSITORY = "Exam-Proctoring"

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

    for config_id, config in configs.items():
        print(f"\n{'='*50}\nSTARTING MODE: {config['name']}\n{'='*50}", flush=True)
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

        for q in questions:
            print(f"\nRunning Q: {q['id']} | Mode: {config_id}")
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
            
            metrics = {
                "question_id": q["id"],
                "mode": config_id,
                "model": MODEL,
                "status": job.status,
                "duration_seconds": duration,
                "input_tokens": getattr(job, "prompt_tokens", 0),
                "output_tokens": getattr(job, "completion_tokens", 0),
                "total_tokens": getattr(job, "prompt_tokens", 0) + getattr(job, "completion_tokens", 0),
                "tool_counts": current_tool_counts.copy(),
                "job_id": job.id,
                "answer": job.messages[-1]["content"] if job.messages else ""
            }
            
            out_file = RAW_RUNS_DIR / f"{config_id}_{q['id']}.json"
            with out_file.open("w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2)
                
            print(f"Finished {q['id']}. Status: {job.status}. Tokens: {metrics['total_tokens']}. Time: {duration:.1f}s")
            print(f"Tools called: {current_tool_counts}")

if __name__ == "__main__":
    run_benchmark()

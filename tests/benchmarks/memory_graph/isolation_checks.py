import json
import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).parent
RAW_RUNS_DIR = BENCHMARK_DIR / "raw_runs"
JOBS_DIR = BENCHMARK_DIR.parent.parent.parent / "backend" / "data" / "jobs"

def run_checks():
    runs = list(RAW_RUNS_DIR.glob("*.json"))
    if not runs:
        print("No raw runs found.")
        sys.exit(1)
        
    failures = 0
    for run_file in runs:
        with run_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
            
        mode = data["mode"]
        job_id = data["job_id"]
        
        if mode == "mode_c":
            continue # Full codexa allows everything
            
        job_file = JOBS_DIR / f"{job_id}.json"
        if not job_file.exists():
            print(f"Warning: Could not find job file {job_file} for run {run_file.name}")
            continue
            
        with job_file.open("r", encoding="utf-8") as f:
            job_data = json.load(f)
            
        # Serialize the entire message history (which includes system prompt, tool results, etc.)
        full_context = json.dumps(job_data.get("messages", [])).lower()
        
        # Check Memory Leakage (Mode A and B)
        memory_keywords = ["adr-004", "project convention strictly dictates", "unauthorized response format", "semantic summary:", "what it does:"]
        
        for kw in memory_keywords:
            if kw in full_context:
                print(f"❌ INVALID - memory leakage detected in {run_file.name}: found '{kw}'")
                failures += 1
                
        # Check Graph Leakage (Mode A)
        if mode == "mode_a":
            graph_keywords = ["called by:", "calls:", "neo4j", "graph lookup", "strata structural"]
            # lookup_symbol returning callers/callees should have "called by:"
            for kw in graph_keywords:
                if kw in full_context:
                    print(f"❌ INVALID - graph leakage detected in {run_file.name}: found '{kw}'")
                    failures += 1
                    
        # Check Tool Usage violations
        if mode == "mode_a":
            forbidden_tools = ["lookup_symbol", "lookup_symbols", "list_symbols", "get_dependencies"]
            for tool in forbidden_tools:
                if data["tool_counts"].get(tool, 0) > 0:
                    print(f"❌ INVALID - tool {tool} was executed in {run_file.name} despite being Mode A.")
                    failures += 1

    if failures == 0:
        print("✅ All Mode A and Mode B runs passed isolation checks. No leakage detected.")
    else:
        print(f"❌ {failures} isolation violations found.")
        sys.exit(1)

if __name__ == "__main__":
    run_checks()

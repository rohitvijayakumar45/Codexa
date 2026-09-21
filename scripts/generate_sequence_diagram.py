"""Fetches high-res SVG and PNG for the Section 6 Sequence Diagram."""

import base64
import urllib.request
from pathlib import Path

mermaid_code = """sequenceDiagram
    autonumber
    actor User
    participant UI as Frontend (graph-viz)
    participant API as FastAPI Router (/chat/agent)
    participant JM as JobManager (jobs.py)
    participant Intent as Intent Classifier (task.py)
    participant Mem as MemoryStore & Context (context.py)
    participant Graph as GraphService & AST
    participant Router as Model Router (llm.py)
    participant Model as LLM Provider (Upstage/Gemini/Z.ai)
    participant Tools as Tool Engine (tools.py)
    participant Verify as Claim Verifier (verification.py)
    participant Disk as Filesystem & Git

    User->>UI: Types request & clicks Send
    UI->>API: POST /chat/agent (repo, message, model)
    API->>JM: JobManager.create() & start in background thread
    API-->>UI: Returns { job_id } immediately (Non-blocking)
    UI->>API: GET /chat/agent/stream/{job_id} (SSE Subscription)
    
    rect rgb(240, 248, 255)
    Note over JM,Intent: Step 1: Task Contract Formulation
    JM->>Intent: classify_intent(message)
    Intent-->>JM: TaskContract (intent=MODIFY_ARTIFACT, required_tools=['edit_file|write_file'])
    end

    rect rgb(255, 250, 240)
    Note over JM,Graph: Step 2: Graph-Anchored Context Assembly
    JM->>Graph: Resolve symbols mentioned in prompt ('auth token refresh')
    Graph-->>JM: Candidate CodeSymbol & File nodes (auth.ts)
    JM->>Mem: 1. Check pre-computed symbol semantic annotations (source="symbol_annotations")
    Mem-->>JM: Return cached symbol purpose & invariant summaries (semantic.py)
    JM->>Graph: 2. 1-to-2 hop AST traversal (calls, imports, depends_on)
    Graph-->>JM: Linked dependency neighborhood & interfaces
    JM->>Mem: 3. Pull procedural, episodic & convention memory records
    Mem-->>JM: Stack conventions, token refresh rules
    end

    rect rgb(245, 255, 245)
    Note over JM,Model: Step 3: Inference & Tool Invocation Loop
    JM->>Router: Select model from heavy tier with failover
    Router->>Model: stream(system_prompt + context + tools)
    Model-->>JM: SSE reasoning chunks (thought tokens streamed to UI)
    Model-->>JM: Tool Call: read_file("src/auth.ts")
    JM->>Tools: execute_tool("read_file")
    Tools->>Disk: Read file contents (Secret check passed)
    Disk-->>Tools: File contents
    Tools-->>JM: Tool Return
    JM->>UI: SSE Event: tool_return
    
    JM->>Model: Next round with tool return in history
    Model-->>JM: SSE reasoning chunks
    Model-->>JM: Tool Call: edit_file("src/auth.ts", old_text, new_text)
    JM->>Tools: execute_tool("edit_file")
    Tools->>Disk: Atomically write patched bytes to disk
    Disk-->>Tools: 0 (Success)
    Tools-->>JM: Tool Return: Success
    end

    rect rgb(255, 240, 245)
    Note over JM,Verify: Step 4: Machine-Gated Completion Validation
    Model-->>JM: Final text response ("I fixed the race condition...")
    JM->>Intent: validate_completion(contract, tools_called)
    Intent-->>JM: Contract Validated (required mutating tool was called)
    JM->>Verify: extract_claims(final_text)
    Verify->>Verify: Deterministically check claims against AST & file on disk
    Verify-->>JM: All claims verified
    JM->>Graph: Trigger background re-index of modified auth.ts
    JM->>Disk: Checkpoint job state to backend/data/jobs/{job_id}.json
    end

    JM->>UI: SSE Event: status = "completed"
    UI-->>User: Renders final response, diff view, and impact summary
"""

def generate():
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    encoded = base64.b64encode(mermaid_code.encode("utf-8")).decode("ascii")

    # 1. Fetch SVG (Vector, infinite zoom, zero blur)
    svg_url = f"https://mermaid.ink/svg/{encoded}"
    print(f"Fetching SVG from {svg_url[:50]}...")
    req = urllib.request.Request(svg_url, headers={"User-Agent": "curl/8.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        svg_bytes = resp.read()
        svg_file = docs_dir / "codexa_e2e_request_lifecycle.svg"
        svg_file.write_bytes(svg_bytes)
        print(f"Saved Vector SVG: {svg_file} ({len(svg_bytes):,} bytes)")

    # 2. Fetch PNG using json payload with mermaid.ink or pako
    try:
        png_url = f"https://mermaid.ink/img/{encoded}"
        print(f"Fetching PNG from {png_url[:50]}...")
        req = urllib.request.Request(png_url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            png_bytes = resp.read()
            png_file = docs_dir / "codexa_e2e_request_lifecycle.png"
            png_file.write_bytes(png_bytes)
            print(f"Saved PNG: {png_file} ({len(png_bytes):,} bytes)")
    except Exception as exc:
        print(f"PNG direct fetch error: {exc}")

    # Also copy to artifacts directory for direct UI viewing
    artifact_dir = Path(r"C:\Users\rohit\.gemini\antigravity\brain\012b28d2-3e87-4aac-a4e4-f7aed6be8f6e")
    if artifact_dir.exists():
        (artifact_dir / "codexa_e2e_request_lifecycle.svg").write_bytes(svg_bytes)
        (artifact_dir / "codexa_e2e_request_lifecycle.png").write_bytes(png_bytes)
        print("Copied to artifacts directory.")

if __name__ == "__main__":
    generate()

"""Part 2: Sections 10 through 17 of Codexa Complete Documentation."""

def get_part2() -> str:
    return r'''## 10. Model and Provider Architecture

Codexa OS implements a multi-provider LLM abstraction layer in `backend/agents/llm.py` (`LLMClient`). The layer wraps `litellm` while adding production reliability guarantees: per-model documented context windows, capability tiers, automatic rate-limit key rotation, and inter-provider failover rings.

### 10.1 Supported Providers
The system connects to **13 distinct model providers**:
1. **Google Gemini**: Vertex/Gemini API via `GEMINI_API_KEY` (supports multi-key rotation `_2`, `_3`, `_4`).
2. **Upstage**: Solar models via `UPSTAGE_API_KEY` (`https://api.upstage.ai/v1`).
3. **Upstage Debug**: Dedicated isolated test provider via `UPSTAGE_DEBUG_API_KEY` (isolated from production rotation pools).
4. **Z.ai (Zhipu AI)**: GLM models via `ZAI_API_KEY` (`https://api.z.ai/api/paas/v4`).
5. **NVIDIA NIM**: Microservices via `NVIDIA_API_KEY` (`https://integrate.api.nvidia.com/v1`).
6. **Groq**: LPU inference engine via `GROQ_API_KEY`.
7. **SiliconFlow**: Open-source models via `SILICONFLOW_API_KEY` (`https://api.siliconflow.com/v1`).
8. **TokenRouter**: Free-tier router via `TOKENROUTER_API_KEY` (`https://api.tokenrouter.com/v1`).
9. **Aerolink**: GPT-5.6 Sol via `AEROLINK_API_KEY` (`https://cgapi.aerolink.lat/v1`).
10. **Cerebras**: Ultra-fast wafer-scale inference via `CEREBRAS_API_KEY`.
11. **Mistral AI**: European frontier models via `MISTRAL_API_KEY`.
12. **AWS Bedrock**: Claude Haiku 4.5 via `AWS_BEARER_TOKEN_BEDROCK`.
13. **Ollama**: Local zero-egress daemon via `OLLAMA_API_BASE` (`http://localhost:11434`).

### 10.2 Capability Tiers and Registered Models
The `MODEL_REGISTRY` maps each model identifier to its human-readable label, real documented context window, capability tier, and provider:

```python
MODEL_REGISTRY: dict[str, tuple[str, int, str, str]] = {
    # Heavy & Ultra-Heavy Tier
    "aerolink/gpt-5.6-sol": ("GPT-5.6 Sol (Aerolink)", 200000, "ultra_heavy", "aerolink"),
    "tokenrouter/z-ai/glm-5.3-free": ("GLM 5.3 (free, TokenRouter)", 128000, "ultra_heavy", "tokenrouter"),
    "siliconflow/deepseek-ai/DeepSeek-V4.1-Flash": ("DeepSeek V4.1 Flash (SiliconFlow)", 128000, "heavy", "siliconflow"),
    "upstage/solar-pro4": ("Solar Pro 4 (Upstage)", 128000, "heavy", "upstage"),
    "gemini/gemini-3.8-flash": ("Gemini 3.8 Flash", 1048576, "heavy", "gemini"),
    "gemini/gemini-3.7-flash": ("Gemini 3.7 Flash", 1048576, "balanced", "gemini"),
    "groq/openai/gpt-oss-120b": ("GPT-OSS 120B (Groq)", 131072, "heavy", "groq"),
    "nvidia_nim/deepseek-ai/deepseek-v4-pro-0813": ("DeepSeek V4 Pro", 128000, "heavy", "nvidia"),
    "nvidia_nim/nvidia/nemotron-3-super-120b-a12b": ("Nemotron 3 Super 120B", 1000000, "heavy", "nvidia"),
    "zai/glm-4.7-flash": ("GLM 4.7 Flash (Z.ai)", 128000, "heavy", "zai"),
    
    # Balanced Tier
    "groq/qwen/qwen3.6-27b": ("Qwen3.6 27B (Groq)", 131072, "balanced", "groq"),
    "cerebras/qwen-3.8-27b": ("Qwen 3.8 27B (Cerebras)", 128000, "balanced", "cerebras"),
    "mistral/mistral-medium-latest": ("Mistral Medium Latest", 128000, "balanced", "mistral"),
    "inception/mercury-2.5": ("Mercury 2.5 (Inception)", 128000, "balanced", "inception"),
    
    # Light Tier (Delegated Workers, Fact Checkers, Subagents)
    "gemini/gemini-3.6-flash": ("Gemini 3.6 Flash", 1048576, "light", "gemini"),
    "gemini/gemini-2.5-flash": ("Gemini 2.5 Flash", 1048576, "light", "gemini"),
    "groq/openai/gpt-oss-20b": ("GPT-OSS 20B (Groq)", 131072, "light", "groq"),
    "groq/groq/compound-mini": ("Compound Mini (Groq)", 131072, "light", "groq"),
    "openrouter/nvidia/nemotron-3.5-lightning:free": ("Nemotron 3.5 Lightning (free)", 1000000, "light", "openrouter"),
    "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0": ("Claude Haiku 4.5 (Bedrock)", 200000, "light", "bedrock"),
    "ollama_chat/josiefied-qwen3:latest": ("Qwen3 8B (Ollama, local)", 40960, "light", "ollama"),
    
    # Debug / Isolated Tier
    "upstage_debug/solar-pro4": ("Solar Pro 4 (Debug/Testing)", 128000, "debug", "upstage_debug"),
}
```

### 10.3 Failover Rings and Key Rotation
To guarantee resilience during long-running tasks, `LLMClient` implements two orthogonal failover mechanisms:
1. **Intra-Provider Key Rotation**: For providers like Gemini or TokenRouter where users configure multiple API keys (`GEMINI_API_KEY`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`), `_active_key_index` tracks the current key. When an HTTP 429 (Rate Limit) or 503 (Overloaded) is encountered, `LLMClient` advances the index and retries with the next key immediately without switching models.
2. **Inter-Provider Failover Rings (`_FAILOVER_RING`)**:
   - `ultra_heavy`: `aerolink/gpt-5.6-sol` -> `upstage/solar-pro4` -> `gemini/gemini-3.8-flash`
   - `heavy`: `upstage/solar-pro4` -> `gemini/gemini-3.8-flash` -> `groq/openai/gpt-oss-120b` -> `gemini/gemini-3.7-flash`
   If all keys for a primary provider are exhausted, the job loop rotates to the next model in the failover ring mid-turn, preserving the entire conversation history and tool state.
3. **Dedicated Worker Ring (`_WORKER_RING`)**:
   Subordinate tasks (such as mechanical code file generation via `delegate_task` or claim extraction in `verification.py`) are routed to `_WORKER_RING`:
   `gemini/gemini-3.8-flash` -> `gemini/gemini-3.7-flash` -> `gemini/gemini-3.6-flash` -> `gemini/gemini-2.5-flash`.
   This keeps expensive orchestrator reasoning quotas completely separate from worker quotas.

---

## 11. Prompt Architecture

Prompt generation in Codexa OS is strictly structured. Prompts are assembled by concatenating typed blocks rather than using free-form strings.

### 11.1 Dynamic Context Assembly Pipeline
For every turn in `backend/agents/jobs.py`, the model input is assembled as:

$$\text{Model Input} = \text{System Prompt} + \text{Task Contract} + \text{Memory Block} + \text{Graph Context} + \text{Design Brief} + \text{Conversation History} + \text{Tool Definitions}$$

1. **System Prompt**: Enforces operating rules, forbids placeholder code, mandates function-calling for file modifications, and forbids markdown summaries when tool calls are required.
2. **Task Contract**: Injected as an authoritative constraint:
   ```
   [TASK CONTRACT]
   Intent: MODIFY_ARTIFACT
   Required Tools: ['edit_file', 'write_file']
   Success Criteria: Ensure the auth refresh token expiration is verified.
   Constraints: Do not modify user session database schema.
   ```
3. **Memory Block (`MemoryStore.context_block`)**: Formats durable records across semantic, procedural, episodic, and organizational tiers.
4. **Graph Context (`ContextAssemblyService`)**: Resolves symbols mentioned in the prompt and extracts their 1-to-2 hop call/import dependencies.
5. **Design Brief (`backend/agents/design_intent.py`)**: When building user interfaces, extracts design principles (e.g. `anti_slop`, `apple_design`, `emil_design_eng`) and injects color palettes, spacing rules, and animation curves.

### 11.2 Specialized Subsystem Prompts
- **Claim Extraction Prompt (`backend/agents/verification.py`)**: Instructs the model to output a strict JSON list of positive, checkable factual claims (`file_exists`, `symbol_exists`, `test_passed`, `action_performed`).
- **Quorum Belief Card Prompt (`backend/agents/quorum.py`)**: Directs independent models to form a structured answer with explicit factual claims and self-assessed confidence scores.
- **Semantic Annotation Prompt (`backend/repository/semantic.py`)**: Analyzes raw function code and generates a one-sentence summary of what the symbol does, its side effects, and invariants.

---

## 12. Reasoning / Thinking Pipeline

Modern frontier models (including DeepSeek-R1, GLM-5.3, Mercury 2.5, and Gemini 2.0/3.0) produce explicit reasoning traces before emitting final text or tool calls.

### 12.1 Streaming and Token Extraction
In `backend/agents/jobs.py` (`_stream_response`), Codexa hooks into raw provider streams and separates reasoning tokens from content tokens:
- **Thinking / Reasoning Tokens**: Emitted as `delta.reasoning_content` (Z.ai, SiliconFlow, DeepSeek) or `delta.thought` (Gemini). Codexa streams these immediately as SSE events with `type: "reasoning_chunk"`. On the frontend, `ThinkingLoader` renders these inside an expandable accordion.
- **Content Tokens**: Emitted as `delta.content`. Streamed as `type: "content_chunk"` and accumulated for final output.
- **Tool Call Chunks**: Emitted as `delta.tool_calls`. Accumulated until the argument JSON block is complete, then dispatched to `tools.execute_tool()`.

### 12.2 Authoring Pathology and Safeguards
During long-running agent builds, autonomous models frequently exhibit an "authoring pathology":
1. **The Pathology**: A model reasons extensively (consuming 10,000–30,000 reasoning tokens) planning how to write a file, approaches its output token ceiling, and runs out of tokens right as it begins writing the actual file content, producing a truncated tool call.
2. **Safeguard 1: Token Budgeting & `_compact_stale_payloads`**: In long multi-round jobs, historical tool arguments (such as a 500-line file written 3 rounds ago) are replaced with `[compacted — 14,200 chars]`. This prevents the input context from exceeding the model's window.
3. **Safeguard 2: Consecutive Cut Detection (`consecutive_cuts`)**: If a model's stream is cut off mid-tool call twice in a row due to output token limits, Codexa intercepts the loop, injects an explicit system directive ("Your previous response was cut short. Use `delegate_task` to offload large file writes to a worker model"), and forces recovery.
4. **Safeguard 3: The Delegation Pattern (`delegate_task` / `delegate_build`)**: To prevent heavy reasoning orchestrators from generating large files twice (once in reasoning, once in tool arguments), orchestrators are instructed to formulate the plan and pass the raw writing to fast worker models.

---

## 13. Tool Architecture

Codexa OS provides **55 distinct tools** exposed via standard OpenAI/JSON function-calling schemas in `backend/agents/tools.py`.

### 13.1 The 8 Tool Groups
To prevent context saturation, Codexa does not expose all 55 tools on every turn. Instead, `classify_intent()` dynamically maps the user request to one or more of **8 tool groups**:

1. **`repo` (Repository Intelligence)**:
   - `read_file`: Reads file content safely.
   - `read_files`: Reads multiple files in a single turn.
   - `list_directory`: Lists directory children.
   - `tree`: Returns nested visual tree of project structure.
   - `search_code`: Fast regex/text search across files.
   - `lookup_symbol`: Queries Knowledge Graph for symbol definition, callers, and callees.
   - `list_symbols`: Lists all functions, classes, and components in a file.
   - `get_dependencies`: Returns incoming and outgoing imports for a symbol/file.
   - `get_project_metadata`: Detects framework, runtime, language, and package managers.
   - `find_references`: Finds all references to a symbol across the graph.
   - `get_file_outline`: Extracts structural outline of a file.
   - `detect_conventions`: Infers indentation, quoting, and architectural naming patterns.
   - `commit_direction`: Records architectural commitments to the memory store.
2. **`code` (Filesystem Mutations)**:
   - `write_file`: Creates or replaces a file with complete content.
   - `edit_file`: Surgically replaces exact old text with new text.
   - `delete_file`: Removes a file or empty directory.
   - `move_file`: Renames or relocates files and directories.
   - `create_directory`: Recursively creates directories.
   - `create_project`: Scaffolds a new project directory structure.
   - `apply_patch`: Applies multi-file atomic patches.
   - `create_files`: Atomically creates multiple files in one call.
3. **`runtime` (Execution & Verification)**:
   - `run_command`: Executes bash/powershell commands with 30s timeout.
   - `run_python`: Executes isolated Python scripts with 10s timeout.
   - `run_tests`: Runs the project test runner (`pytest`, `npm test`) and parses output.
   - `typecheck`: Runs `tsc` or `mypy` and returns structured error locations.
   - `lint`: Runs linter (`eslint`, `ruff`) returning structured warnings.
   - `build`: Runs production build pipeline (`vite build`, `next build`).
   - `get_build_errors`: Retrieves structured error diagnostics from the last build.
   - `start_dev_server`: Boots local dev server and returns the local URL.
4. **`browser` (Web & UI Automation)**:
   - `screenshot`: Captures viewport rendering of a local URL.
   - `browser_navigate`: Navigates headless browser to a route.
   - `browser_click`: Clicks elements by CSS selector.
   - `browser_type`: Enters text into form inputs.
   - `browser_console`: Inspects browser console errors and logs.
   - `browser_network`: Evaluates HTTP network requests and failed assets.
   - `browser_scroll`: Scrolls viewport by $(x, y)$ pixels.
   - `inspect_element`: Extracts computed CSS styles, layout dimensions, and a11y attributes.
   - `inspect_page`: Full page audit (DOM structure, console errors, performance).
5. **`design` (Design Intelligence)**:
   - `get_design_guidance`: Loads specialized design guides (`anti_slop`, `apple_design`, `emil_design_eng`).
   - `get_design_system`: Extracts colors, typography, spacing, and shadows from Tailwind/CSS.
   - `analyze_visual_hierarchy`: Evaluates layout contrast and typography hierarchy.
   - `check_design_consistency`: Identifies inconsistent spacing or colors across files.
   - `inspect_component`: Inspects props, styles, and usage counts of UI components.
6. **`git` (Version Control)**:
   - `git_status`: Shows modified, untracked, and deleted files.
   - `git_diff`: Displays exact staged/unstaged code diffs.
   - `git_log`: Inspects recent commit history.
   - `git_branch`: Lists branches and active branch.
   - `create_branch`: Creates and checks out a new branch.
   - `commit`: Stages changes and commits with conventional commit message.
   - `summarize_changes`: Summarizes lines added/removed, risk score, and test status.
7. **`external` (External Intelligence)**:
   - `web_search`: Queries public web via Tavily API for current documentation.
   - `semantic_search`: Queries embeddings for natural language code discovery.
8. **`orchestration` (Worker Delegation)**:
   - `delegate_task`: Offloads mechanical writing of pre-planned files to a fast worker model.
   - `delegate_build`: Passes high-level spec to a worker that writes code and saves files.
   - `generate_with_qwen`: Employs Qwen Plus Character on a dedicated quota for text/code drafting.

### 13.2 Security Filters and Execution Guards
`backend/agents/tools.py` enforces three deterministic security gates before dispatching any tool:
1. **Platform Mutation Guard (`_MUTATING_TOOLS`)**:
   Codexa OS strictly refuses to mutate its own source repository through agent tools. The guard intercepts all 18 mutating tools (`write_file`, `edit_file`, `delete_file`, `run_command`, `run_python`, etc.). If `repository == "codexa-os"` (or resolves to the platform worktree), execution raises:
   ```
   PermissionError: Refused to mutate platform repository: Codexa OS source code cannot be modified via agent tools.
   ```
2. **Secret File Exclusion (`_SECRET_FILENAMES`)**:
   Tools that read files (`read_file`, `read_files`) intercept access to credential stores (`.env`, `.env.local`, `credentials.json`, `id_rsa`, `*.pem`, `*.key`). The request is refused before opening the file, preventing secrets from leaking into LLM transcripts or persisted job checkpoints.
3. **Compacted Payload Defense (`_COMPACTED_MARK`)**:
   If an agent attempts to call `write_file` with content beginning with `"[compacted"`, the write is rejected. This prevents the agent from overwriting real source files with conversation truncation markers.

---

## 14. File Editing System

File mutations in Codexa OS are atomic and verifiable. The platform provides two primary editing interfaces: `write_file` (full file replacement) and `edit_file` (surgical chunk replacement).

### 14.1 Surgical Chunk Editing (`edit_file`)
`edit_file` requires three parameters: `path`, `old_text`, and `new_text`.
- **Exact Match Requirement**: The target file is read from disk. The system verifies that `old_text` exists in the file *exactly once*.
- **Ambiguity Guard**: If `old_text` appears multiple times, the tool raises an error requiring the agent to provide more surrounding context lines to make the match unique.
- **Diff Feedback**: Upon replacement, the tool returns the line numbers affected and a unified diff snippet, allowing the model to confirm the change in its next turn.

### 14.2 Atomic Write & Windows OneDrive Lock Mitigation
On Windows environments where the repository lives inside a synchronized directory (e.g. OneDrive), background file indexing locks files intermittently. An ordinary `os.replace` fails with `[WinError 5] Access is denied`.

`backend/files/api.py` and `backend/agents/jobs.py` implement an exponential backoff retry loop around all atomic file replacements:
```python
for attempt in range(5):
    try:
        temp_file.replace(target_file)
        break
    except PermissionError:
        time.sleep(0.05 * (2 ** attempt))
else:
    # Fallback to direct write if atomic rename is permanently locked
    target_file.write_text(content, encoding="utf-8")
```

---

## 15. Repository Intelligence

When a repository is imported via `POST /repository/load`, Codexa boots an end-to-end intelligence ingestion pipeline.

```mermaid
flowchart TD
    Repo[Cloned / Loaded Repository] --> Step1[1. File Discovery & Extension Filter]
    Step1 --> Step2[2. Tree-sitter AST Parsing: analyze.py]
    Step1 --> Step3[3. Git History Mining: coupling.py]
    Step1 --> Step4[4. Route & Manifest Extraction: intent.py]
    
    Step2 --> Symbols[Symbols, Functions, Classes, Calls, Imports]
    Step3 --> Coupling[Change Coupling Edges: CORRELATES_WITH]
    Step4 --> Routes[API Routes, Architectural Decisions]

    Symbols --> EKG[(Engineering Knowledge Graph)]
    Coupling --> EKG
    Routes --> EKG

    EKG --> Step5[5. Memory Bundle Generation]
    Step5 --> MemStore[(MemoryStore: .codexa/memories.json)]
    EKG --> Step6[6. Architecture Health Scoring: scoring.py]
```

### 15.1 In-Memory Graph Seeding (`backend/seed.py`)
To enable instantaneous out-of-the-box local development without requiring external database services, setting `CODEXA_SEED=1` executes `seed_graph()`. This routine populates the in-memory graph with a self-referential model of Codexa OS itself:
- Creates repository root node `repo://codexa-os`.
- Models core backend and frontend modules as `File` nodes.
- Establishes `calls`, `imports`, and `depends_on` relationships between services.
- Seeds historical `CausalEvent` and `PreventionRule` nodes representing real system invariants.

### 15.2 Dynamic Re-Indexing
Whenever an agent executes a tool in `GRAPH_DIRTYING_TOOLS` (`write_file`, `edit_file`, `delete_file`, `apply_patch`), or a developer saves a file in the frontend IDE (`POST /files/save`), Codexa triggers `reindex_repository()`. The modified files are immediately re-parsed with Tree-sitter, updating the Knowledge Graph before the next agent turn or user query.

---

## 16. Tree-sitter / Static Analysis

Static analysis in Codexa OS is powered by official Tree-sitter native grammars in `backend/repository/analyze.py`.

### 16.1 Supported Grammars
- **Python**: `tree_sitter_python` (`_PY_LANG`)
- **JavaScript**: `tree_sitter_javascript` (`_JS_LANG`)
- **TypeScript**: `tree_sitter_typescript.language_typescript()` (`_TS_LANG`)
- **TSX / JSX**: `tree_sitter_typescript.language_tsx()` (`_TSX_LANG`)

### 16.2 AST Query Extraction
Codexa uses compiled Tree-sitter S-expression queries to extract symbol definitions and call sites with syntax-aware precision:
```scheme
;; Python Definition and Call Query
(function_definition name: (identifier) @def.name) @def.node
(class_definition name: (identifier) @def.name) @def.node
(call function: (identifier) @call.name)
(call function: (attribute attribute: (identifier) @call.name))
```
- **Scope Attribution**: Calls are attributed strictly to the enclosing function or method node by walking parent pointers in the Tree-sitter AST, eliminating regex false positives.
- **Syntax Error Resilience**: Tree-sitter produces a concrete syntax tree even when encountering malformed or incomplete code files. Unparseable tokens become `ERROR` nodes while surrounding valid functions are extracted cleanly.
- **Analysis Caps**: To ensure sub-second indexing on large repositories, extraction is bounded:
  - `_MAX_FILES = 1,500` source files
  - `_MAX_ALL_FILES = 6,000` total project files
  - `_MAX_SYMBOLS = 4,000` symbols
  - `_MAX_EDGES = 8,000` call/import edges
  - `_MAX_FILE_BYTES = 1,000,000` bytes (1 MB file size limit)

---

## 17. Symbol Intelligence

Extracted symbols are converted into first-class `CodeSymbol` nodes in the Knowledge Graph.

### 17.1 Symbol Schema and Identifiers
Every symbol receives a globally deterministic stable ID:
`symbol://{repository}/{posix_file_path}#{symbol_name}:{line_number}`

Properties attached to each symbol node include:
- `name`: Identifier name (e.g. `validate_completion`).
- `kind`: `function`, `class`, `method`, `component`, or `hook`.
- `file`: Path relative to repository root.
- `line`: Starting line number (1-indexed).
- `end_line`: Terminating line number from AST node span.
- `content_hash`: SHA-256 hash of the symbol's raw text for cache invalidation.

### 17.2 LLM Semantic Summarization (`backend/repository/semantic.py`)
In addition to static AST data, symbols undergo asynchronous semantic annotation:
1. `annotate_symbol()` extracts the raw implementation bytes of the symbol.
2. Dispatches a concise completion request to a light-tier model.
3. Produces a two-part annotation:
   - `summary`: One sentence explaining what the symbol accomplishes.
   - `behavior`: Invariants, expected exceptions, and external side effects.
4. The annotation is saved to the `CodeSymbol` properties and indexed for natural-language semantic discovery via `lookup_symbol`.

---
'''

if __name__ == '__main__':
    print(f"Part 2 length: {len(get_part2())} characters, ~{len(get_part2().split())} words")

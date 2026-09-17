import tempfile
from pathlib import Path
from uuid import uuid4

from backend.repository.analyze import analyze_repo
from backend.repository.intent import extract_routes, extract_decisions
from backend.graph.service import GraphService
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.events import InMemoryGraphEventWriter
from backend.graph.schemas import GraphNodeCreate, GraphNodeType, GraphNodeProvenance
from backend.memory.store import MemoryStore
from backend.memory.context import _relevance_score
from backend.agents.task import classify_intent, generate_contract, validate_completion
from backend.agents.tools import execute_tool, parse_args
from backend.agents.quorum import QuorumService, BeliefCard, BeliefCardClaim


def test_scenario_a_repo_ingestion_treesitter_to_graph():
    """SCENARIO A: Repository ingestion -> Tree-sitter -> graph node extraction."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "app.py").write_text("def run():\n    return 'hello'\n", encoding="utf-8")

        analysis = analyze_repo(root)
        repo = InMemoryGraphRepository()
        svc = GraphService(repository=repo, event_writer=InMemoryGraphEventWriter())

        # Ingest file node
        f_node = svc.add_node(GraphNodeCreate(
            node_type=GraphNodeType.FILE,
            stable_id="app.py",
            properties={"path": "app.py"},
            provenance=GraphNodeProvenance.INTERNAL_CODE,
        ))
        
        # Ingest symbol node
        for sym in analysis.symbols:
            s_node = svc.add_node(GraphNodeCreate(
                node_type=GraphNodeType.CODE_SYMBOL,
                stable_id=f"app.py:{sym.name}",
                properties={"name": sym.name, "file": sym.file, "line": sym.line},
                provenance=GraphNodeProvenance.INTERNAL_CODE,
            ))
            assert s_node.id is not None

        nodes = svc.repository.list_nodes()
        assert len(nodes) >= 2


def test_scenario_b_user_query_retrieval_memory_and_graph():
    """SCENARIO B: User query -> memory context relevance scoring."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_file = Path(tmpdir) / "mem.json"
        store = MemoryStore(path=mem_file)
        store.add(
            repository="test-repo",
            memory_type="procedural",
            title="Deploy Instructions",
            content="Run docker compose up to start services",
        )

        score = _relevance_score(
            query="how do I start services?",
            title="Deploy Instructions",
            content="Run docker compose up to start services",
            memory_type="procedural"
        )
        assert score > 0.5


def test_scenario_c_planning_tool_call_and_validation():
    """SCENARIO C: Agent modifies code -> planning -> tool call -> validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create initial file
        (root / "target.py").write_text("def placeholder(): pass\n", encoding="utf-8")

        # 1. Intent & Contract
        contract = generate_contract("edit target.py to implement real logic")
        
        # 2. Simulated tool execution
        tool_res = execute_tool("write_file", {"path": "target.py", "content": "def real_logic(): return 1"}, repository="sample-repo")
        
        # 3. Post-hoc validation
        passed, msg = validate_completion(contract, tools_called=["write_file"])
        assert passed is True


def test_scenario_d_negative_malformed_tool_args():
    """NEGATIVE TEST: Malformed tool arguments return informative error, no crash."""
    # Invalid JSON / missing required argument
    parsed = parse_args("not-a-json-object")
    assert isinstance(parsed, dict)
    
    # Missing required argument in execute_tool
    res = execute_tool("read_file", {}, repository="sample-repo")
    assert "failed" in res.lower() or "error" in res.lower() or "missing" in res.lower()


def test_scenario_e_negative_missing_file():
    """NEGATIVE TEST: Reading a nonexistent file returns graceful error, no unhandled exception."""
    res = execute_tool("read_file", {"path": "does_not_exist_at_all.xyz"}, repository="sample-repo")
    assert "failed" in res.lower() or "does not exist" in res.lower() or "not loaded" in res.lower()

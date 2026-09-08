"""Tests for graph-state witness hashing (backend/simulation/witness.py) and its wiring into the
simulate-to-execute integrity check (backend/simulation/engine.py, backend/execution/sandbox.py)."""

from types import SimpleNamespace
from uuid import UUID, uuid4

from backend.simulation.witness import hash_graph_state


def _node(node_id, node_type="CodeSymbol", **properties):
    return SimpleNamespace(id=node_id, node_type=node_type, properties=properties)


class FakeGraph:
    def __init__(self, nodes):
        self._nodes = nodes

    def list_nodes(self):
        return self._nodes


class TestHashGraphState:
    def test_empty_node_set_hashes_consistently(self):
        assert hash_graph_state(set(), graph=FakeGraph([])) == hash_graph_state(set(), graph=FakeGraph([_node(uuid4())]))

    def test_same_state_hashes_identically(self):
        nid = uuid4()
        graph = FakeGraph([_node(nid, name="foo", line=10)])

        h1 = hash_graph_state({nid}, graph=graph)
        h2 = hash_graph_state({nid}, graph=graph)

        assert h1 == h2

    def test_changed_property_changes_the_hash(self):
        nid = uuid4()
        graph_before = FakeGraph([_node(nid, name="foo", line=10)])
        graph_after = FakeGraph([_node(nid, name="foo", line=42)])  # symbol moved lines

        assert hash_graph_state({nid}, graph=graph_before) != hash_graph_state({nid}, graph=graph_after)

    def test_deleted_node_changes_the_hash(self):
        nid = uuid4()
        graph_before = FakeGraph([_node(nid, name="foo")])
        graph_after = FakeGraph([])  # node removed entirely (e.g. file deleted, symbol gone)

        assert hash_graph_state({nid}, graph=graph_before) != hash_graph_state({nid}, graph=graph_after)

    def test_node_order_does_not_affect_the_hash(self):
        a, b = uuid4(), uuid4()
        graph_ab = FakeGraph([_node(a, name="a"), _node(b, name="b")])
        graph_ba = FakeGraph([_node(b, name="b"), _node(a, name="a")])

        assert hash_graph_state({a, b}, graph=graph_ab) == hash_graph_state({a, b}, graph=graph_ba)

    def test_nodes_outside_the_requested_set_are_ignored(self):
        wanted, unrelated = uuid4(), uuid4()
        graph_without_unrelated = FakeGraph([_node(wanted, name="foo")])
        graph_with_unrelated = FakeGraph([_node(wanted, name="foo"), _node(unrelated, name="bar")])

        assert hash_graph_state({wanted}, graph=graph_without_unrelated) == hash_graph_state({wanted}, graph=graph_with_unrelated)

    def test_a_new_unrelated_node_appearing_does_not_change_an_unrelated_hash(self):
        # Complements the above: confirms the hash is scoped to the witness set, not the whole graph.
        a = uuid4()
        graph1 = FakeGraph([_node(a, name="a")])
        graph2 = FakeGraph([_node(a, name="a"), _node(uuid4(), name="new_unrelated_symbol")])

        assert hash_graph_state({a}, graph=graph1) == hash_graph_state({a}, graph=graph2)


class TestEngineSandboxIntegration:
    def test_simulation_then_sandbox_with_unchanged_graph_is_not_blocked_by_witness(self):
        from backend.execution.sandbox import SandboxExecutionService, SandboxRunRequest, SandboxCommand
        from backend.simulation.engine import EngineeringSimulationEngine, SimulationRequest
        from backend.agents.planner import PlannerService
        from backend.graph.repository import InMemoryGraphRepository
        from backend.graph.events import InMemoryGraphEventWriter
        from backend.graph.service import GraphService
        from backend.graph.schemas import GraphNodeCreate, GraphNodeType

        event_writer = InMemoryGraphEventWriter()
        graph = GraphService(repository=InMemoryGraphRepository(), event_writer=event_writer)
        target = graph.add_node(GraphNodeCreate(node_type=GraphNodeType.CODE_SYMBOL, stable_id="symbol://target", properties={"name": "target_fn"}))

        planner = PlannerService(repository=graph.repository, event_writer=event_writer, llm=None)
        engine = EngineeringSimulationEngine(graph=graph, planner=planner)
        sandbox = SandboxExecutionService(event_writer=event_writer, graph=graph)

        sim_result = engine.run(SimulationRequest(
            proposal_id=uuid4(), changed_node_ids=[target.id], diff_text="def target_fn(): pass",
            deployment_steps=["deploy"], rollback_steps=["restore from backup"],
        ))

        run_result = sandbox.schedule_run(SandboxRunRequest(
            proposal_id=sim_result.proposal_id, diff_text="def target_fn(): pass",
            commands=[SandboxCommand(command="pytest")],
        ))

        assert "graph_state_changed" not in run_result.blocked_reasons

    def test_graph_mutation_between_simulate_and_execute_is_blocked(self):
        from backend.execution.sandbox import SandboxExecutionService, SandboxRunRequest, SandboxCommand
        from backend.simulation.engine import EngineeringSimulationEngine, SimulationRequest
        from backend.agents.planner import PlannerService
        from backend.graph.repository import InMemoryGraphRepository
        from backend.graph.events import InMemoryGraphEventWriter
        from backend.graph.service import GraphService
        from backend.graph.schemas import GraphNodeCreate, GraphNodeType

        event_writer = InMemoryGraphEventWriter()
        graph = GraphService(repository=InMemoryGraphRepository(), event_writer=event_writer)
        target = graph.add_node(GraphNodeCreate(node_type=GraphNodeType.CODE_SYMBOL, stable_id="symbol://target", properties={"name": "target_fn", "line": 10}))

        planner = PlannerService(repository=graph.repository, event_writer=event_writer, llm=None)
        engine = EngineeringSimulationEngine(graph=graph, planner=planner)
        sandbox = SandboxExecutionService(event_writer=event_writer, graph=graph)

        sim_result = engine.run(SimulationRequest(
            proposal_id=uuid4(), changed_node_ids=[target.id], diff_text="def target_fn(): pass",
            deployment_steps=["deploy"], rollback_steps=["restore from backup"],
        ))

        # Something changes the witnessed node's structural state between simulate and execute —
        # e.g. a reindex after a concurrent edit moved the symbol to a different line.
        graph.add_node(GraphNodeCreate(node_type=GraphNodeType.CODE_SYMBOL, stable_id="symbol://target", properties={"name": "target_fn", "line": 99}))

        run_result = sandbox.schedule_run(SandboxRunRequest(
            proposal_id=sim_result.proposal_id, diff_text="def target_fn(): pass",  # same diff text
            commands=[SandboxCommand(command="pytest")],
        ))

        assert "graph_state_changed" in run_result.blocked_reasons
        assert "simulation_content_mismatch" not in run_result.blocked_reasons  # the diff itself didn't change

    def test_old_scenario_with_no_witness_fields_is_not_falsely_blocked(self):
        # Backward compatibility: a SimulationScenario node written before this feature existed has
        # no graph_state_hash/witness_node_ids at all — must not be treated as a mismatch.
        from backend.execution.sandbox import SandboxExecutionService, SandboxRunRequest, SandboxCommand
        from backend.graph.repository import InMemoryGraphRepository
        from backend.graph.events import InMemoryGraphEventWriter
        from backend.graph.service import GraphService
        from backend.graph.schemas import GraphNodeCreate, GraphNodeType
        import hashlib

        event_writer = InMemoryGraphEventWriter()
        graph = GraphService(repository=InMemoryGraphRepository(), event_writer=event_writer)
        proposal_id = uuid4()
        diff_text = "def f(): pass"
        graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.SIMULATION_SCENARIO, stable_id="simulation://old",
            properties={
                "proposal_id": str(proposal_id), "status": "passed",
                "diff_hash": hashlib.sha256(diff_text.encode()).hexdigest(),
                # no graph_state_hash / witness_node_ids — pre-feature record
            },
        ))
        sandbox = SandboxExecutionService(event_writer=event_writer, graph=graph)

        run_result = sandbox.schedule_run(SandboxRunRequest(
            proposal_id=proposal_id, diff_text=diff_text, commands=[SandboxCommand(command="pytest")],
        ))

        assert run_result.blocked_reasons == []

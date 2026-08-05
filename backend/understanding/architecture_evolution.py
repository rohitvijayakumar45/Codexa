from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.graph.schemas import (
    GraphEdgeCreate,
    GraphEdgeSourceType,
    GraphEdgeType,
    GraphNodeCreate,
    GraphNodeType,
)
from backend.graph.service import GraphService


class ArchitectureObservation(BaseModel):
    observed_at: datetime
    coupling: float = Field(ge=0)
    cohesion: float = Field(ge=0)
    cyclomatic_complexity: float = Field(ge=0)
    fan_in: float = Field(ge=0)
    fan_out: float = Field(ge=0)
    ownership_fragmentation: float = Field(ge=0)
    file_churn: float = Field(ge=0)


class ArchitectureTrendRequest(BaseModel):
    module_path: str = Field(min_length=1, max_length=1024)
    observations: list[ArchitectureObservation] = Field(min_length=2)


class MetricTrend(BaseModel):
    metric: str
    first_value: float
    latest_value: float
    slope_per_day: float


class ArchitectureTrendResult(BaseModel):
    trend_node_id: UUID
    module_path: str
    trends: list[MetricTrend]
    alerts: list[str]
    bottleneck_eta_days: float | None


class ArchitectureEvolutionService:
    bottleneck_coupling_threshold = 1.0

    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def record_trend(self, request: ArchitectureTrendRequest) -> ArchitectureTrendResult:
        ordered = sorted(request.observations, key=lambda observation: observation.observed_at)
        trends = [
            self._trend(metric, ordered)
            for metric in [
                "coupling",
                "cohesion",
                "cyclomatic_complexity",
                "fan_in",
                "fan_out",
                "ownership_fragmentation",
                "file_churn",
            ]
        ]
        alerts = self._alerts(trends)
        bottleneck_eta_days = self._bottleneck_eta_days(trends)
        module = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.FILE,
                stable_id=f"file://{request.module_path}",
                properties={"path": request.module_path, "kind": "module"},
            )
        )
        node = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.ARCHITECTURE_TREND,
                stable_id=f"architecture-trend://{request.module_path}",
                properties={
                    "module_path": request.module_path,
                    "trends": [trend.model_dump() for trend in trends],
                    "alerts": alerts,
                    "bottleneck_eta_days": bottleneck_eta_days,
                },
            )
        )
        self.graph.add_edge(
            GraphEdgeCreate(
                from_node_id=node.id,
                to_node_id=module.id,
                edge_type=GraphEdgeType.DERIVED_FROM,
                confidence=1.0,
                source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
                valid_from=ordered[-1].observed_at,
                properties={"metric_window_size": len(ordered)},
            )
        )
        return ArchitectureTrendResult(
            trend_node_id=node.id,
            module_path=request.module_path,
            trends=trends,
            alerts=alerts,
            bottleneck_eta_days=bottleneck_eta_days,
        )

    def list_trends(self) -> list[ArchitectureTrendResult]:
        results: list[ArchitectureTrendResult] = []
        for node in self.graph.list_nodes():
            if node.node_type != GraphNodeType.ARCHITECTURE_TREND:
                continue

            properties = node.properties
            results.append(
                ArchitectureTrendResult(
                    trend_node_id=node.id,
                    module_path=properties["module_path"],
                    trends=[MetricTrend(**trend) for trend in properties.get("trends", [])],
                    alerts=list(properties.get("alerts", [])),
                    bottleneck_eta_days=properties.get("bottleneck_eta_days"),
                )
            )
        return sorted(results, key=lambda result: result.module_path)

    def _trend(
        self, metric: str, observations: list[ArchitectureObservation]
    ) -> MetricTrend:
        first = observations[0]
        latest = observations[-1]
        elapsed_days = max((latest.observed_at - first.observed_at).total_seconds() / 86400, 1)
        first_value = float(getattr(first, metric))
        latest_value = float(getattr(latest, metric))
        return MetricTrend(
            metric=metric,
            first_value=first_value,
            latest_value=latest_value,
            slope_per_day=(latest_value - first_value) / elapsed_days,
        )

    def _alerts(self, trends: list[MetricTrend]) -> list[str]:
        alerts: list[str] = []
        by_metric = {trend.metric: trend for trend in trends}
        coupling = by_metric["coupling"]
        if coupling.first_value > 0:
            growth = (coupling.latest_value - coupling.first_value) / coupling.first_value
            if growth >= 0.4:
                alerts.append("coupling_growth_over_40_percent")
        if by_metric["cyclomatic_complexity"].slope_per_day > 0:
            alerts.append("complexity_increasing")
        if by_metric["ownership_fragmentation"].slope_per_day > 0:
            alerts.append("ownership_fragmentation_increasing")
        return alerts

    def _bottleneck_eta_days(self, trends: list[MetricTrend]) -> float | None:
        coupling = next(trend for trend in trends if trend.metric == "coupling")
        if coupling.slope_per_day <= 0 or coupling.latest_value >= self.bottleneck_coupling_threshold:
            return None
        return (self.bottleneck_coupling_threshold - coupling.latest_value) / coupling.slope_per_day

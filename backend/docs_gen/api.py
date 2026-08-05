"""Generated documentation, drawn from the live API surface.

Documentation is produced by introspecting the running FastAPI app: real routes, real request and
response models, real fields. This is deterministic and always available. When a language model is
configured and reachable, it can additionally write the prose overview (opt-in via ?llm=true);
otherwise a grounded deterministic overview is used. Results are cached; POST /docs/regenerate
rebuilds on demand rather than regenerating on every load.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any, get_args

from fastapi import APIRouter, Query, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel

from backend.agents.llm import LLMClient

_OVERVIEW = (
    "Codexa OS is an engineering intelligence platform built around a temporal, confidence-weighted "
    "Engineering Knowledge Graph. A FastAPI backend ingests engineering artifacts, projects them into "
    "the graph, and runs cognitive subsystems over it: planning and blast-radius analysis, a digital-twin "
    "simulation engine, causal reasoning, architecture-evolution tracking, repository health scoring, "
    "incident learning, and policy distillation. Untrusted content is isolated at a trust boundary and can "
    "never trigger tools directly. Every graph edge records its confidence and how it was asserted "
    "(static analysis, LLM inference, or human assertion), and carries temporal validity so the graph can "
    "be replayed at any point in its history."
)


class FieldDoc(BaseModel):
    name: str
    type: str
    required: bool
    description: str | None = None


class ModelDoc(BaseModel):
    name: str
    fields: list[FieldDoc]


class EndpointDoc(BaseModel):
    method: str
    path: str
    name: str
    summary: str | None
    request_model: str | None
    response_model: str | None


class GroupDoc(BaseModel):
    tag: str
    endpoints: list[EndpointDoc]


class GeneratedDocs(BaseModel):
    generated_at: datetime
    overview: str
    groups: list[GroupDoc]
    models: list[ModelDoc]


_cache: dict[str, GeneratedDocs] = {}


def _type_str(annotation: Any) -> str:
    if annotation is None:
        return "any"
    name = getattr(annotation, "__name__", None)
    if name:
        return name
    return str(annotation).replace("typing.", "").replace("backend.", "")


def _model_doc(model: type[BaseModel]) -> ModelDoc:
    fields = [
        FieldDoc(
            name=field_name,
            type=_type_str(field.annotation),
            required=field.is_required(),
            description=field.description,
        )
        for field_name, field in model.model_fields.items()
    ]
    return ModelDoc(name=model.__name__, fields=fields)


def _unwrap_models(annotation: Any) -> list[type[BaseModel]]:
    found: list[type[BaseModel]] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        found.append(annotation)
    for arg in get_args(annotation):
        found.extend(_unwrap_models(arg))
    return found


def _request_model(route: APIRoute) -> type[BaseModel] | None:
    body_field = getattr(route, "body_field", None)
    if body_field is not None:
        annotation = getattr(body_field, "type_", None)
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation
    # Fall back to scanning the endpoint signature for a Pydantic parameter.
    try:
        for param in inspect.signature(route.endpoint).parameters.values():
            ann = param.annotation
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                return ann
    except (ValueError, TypeError):
        pass
    return None


def _iter_api_routes(routes: list[Any]) -> list[APIRoute]:
    # FastAPI 0.141+ keeps included routers nested (_IncludedRouter) rather than flattening their
    # APIRoutes into app.routes, so we recurse into anything that carries its own .routes.
    found: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        # A plain APIRouter exposes .routes; FastAPI 0.141's _IncludedRouter wraps the original
        # router under .original_router instead.
        original = getattr(route, "original_router", None)
        sub = getattr(route, "routes", None) or getattr(original, "routes", None)
        if sub:
            found.extend(_iter_api_routes(list(sub)))
    return found


def _build(routes: list[Any], *, llm: LLMClient | None, use_llm: bool) -> GeneratedDocs:
    groups: dict[str, list[EndpointDoc]] = {}
    models: dict[str, ModelDoc] = {}

    for route in _iter_api_routes(routes):
        if route.path.startswith("/openapi"):
            continue
        tag = (route.tags[0] if route.tags else "general") if hasattr(route, "tags") else "general"
        request_model = _request_model(route)
        response_models = _unwrap_models(route.response_model)
        summary = (route.endpoint.__doc__ or "").strip().split("\n")[0] or None

        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            groups.setdefault(str(tag), []).append(
                EndpointDoc(
                    method=method,
                    path=route.path,
                    name=route.name,
                    summary=summary,
                    request_model=request_model.__name__ if request_model else None,
                    response_model=response_models[0].__name__ if response_models else None,
                )
            )
        for model in ([request_model] if request_model else []) + response_models:
            if model.__name__ not in models:
                models[model.__name__] = _model_doc(model)

    overview = _OVERVIEW
    if use_llm and llm is not None:
        try:
            overview = llm.generate(
                "docs",
                "Write a concise 2-paragraph developer overview of this system:\n" + _OVERVIEW,
            ) or _OVERVIEW
        except Exception:  # noqa: BLE001 - never let a missing model break docs
            overview = _OVERVIEW

    ordered_groups = [
        GroupDoc(tag=tag, endpoints=sorted(eps, key=lambda e: (e.path, e.method)))
        for tag, eps in sorted(groups.items())
    ]
    return GeneratedDocs(
        generated_at=datetime.now(UTC),
        overview=overview,
        groups=ordered_groups,
        models=sorted(models.values(), key=lambda m: m.name),
    )


def create_docs_router(*, llm: LLMClient) -> APIRouter:
    router = APIRouter(prefix="/docs-gen", tags=["documentation"])

    @router.get("/generated", response_model=GeneratedDocs)
    def get_docs(request: Request) -> GeneratedDocs:
        if "docs" not in _cache:
            _cache["docs"] = _build(list(request.app.routes), llm=llm, use_llm=False)
        return _cache["docs"]

    @router.post("/regenerate", response_model=GeneratedDocs)
    def regenerate(request: Request, llm_prose: bool = Query(default=False)) -> GeneratedDocs:
        _cache["docs"] = _build(list(request.app.routes), llm=llm, use_llm=llm_prose)
        return _cache["docs"]

    return router

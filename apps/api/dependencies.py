from __future__ import annotations

import os
from typing import Optional
from fastapi import Header, Request
from core.state.store import StateStore
from core.models.router import ModelRouter

_DEFAULT_DB_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///deep_research_local.db"
)

# Global router instance
_model_router = ModelRouter()


def get_model_router() -> ModelRouter:
    return _model_router


def get_tenant_id(
    request: Request,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> str:
    # Allow path param tenant_id if present
    tenant_id = request.path_params.get("tenant_id") or request.path_params.get("id")
    if x_tenant_id:
        return x_tenant_id
    if tenant_id and "tenant" in tenant_id:
        return tenant_id
    return os.environ.get("DEFAULT_TENANT_ID", "tenant_default")


def get_state_store(tenant_id: Optional[str] = None) -> StateStore:
    tid = tenant_id or os.environ.get("DEFAULT_TENANT_ID", "tenant_default")
    return StateStore(tenant_id=tid, db_url=_DEFAULT_DB_URL)

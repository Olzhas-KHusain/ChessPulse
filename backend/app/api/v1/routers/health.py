"""Liveness endpoint (unversioned operational endpoint; does not query the database)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "service": "chesspulse-backend",
        "version": __version__,
        "environment": request.app.state.settings.app_env,
    }

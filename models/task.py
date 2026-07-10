"""Shared task response models."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


class TaskDispatchInfo(BaseModel):
    backend: str
    task_id: Optional[str] = None
    fallback_reason: Optional[str] = None
    state: Optional[str] = None
    ready: Optional[bool] = None
    successful: Optional[bool] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

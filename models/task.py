"""Shared task response models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class TaskDispatchInfo(BaseModel):
    backend: str
    task_id: Optional[str] = None
    fallback_reason: Optional[str] = None

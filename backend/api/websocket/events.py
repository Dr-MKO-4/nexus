"""Types d'événements WebSocket  Prompt 7.2."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, enum.Enum):
    AGENT_STATUS = "agent_status"
    TASK_PROGRESS = "task_progress"
    HITL_INTERRUPT = "hitl_interrupt"
    HITL_RESOLVED = "hitl_resolved"
    CONTENT_STREAM = "content_stream"
    ALERT = "alert"
    BUDGET_UPDATE = "budget_update"
    CAMPAIGN_UPDATE = "campaign_update"
    REPORT_READY = "report_ready"


class WebSocketMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    campaign_id: Optional[str] = None
    agent_name: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    timestamp: datetime
    trace_id: str


__all__ = ["EventType", "WebSocketMessage"]

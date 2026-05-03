from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


# Inbound request models

class ContextPush(BaseModel):
    scope: Literal["category", "merchant", "customer", "trigger"]
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = []


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int


# Outbound response models

class ContextAck(BaseModel):
    accepted: bool
    ack_id: Optional[str] = None
    stored_at: Optional[str] = None
    reason: Optional[str] = None
    current_version: Optional[int] = None


class TickAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: Literal["vera", "merchant_on_behalf"]
    trigger_id: str
    template_name: str
    template_params: list[str]
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[TickAction]


class ReplyResponse(BaseModel):
    action: Literal["send", "wait", "end"]
    body: Optional[str] = None
    cta: Optional[str] = None
    rationale: str
    wait_seconds: Optional[int] = None


# Internal pipeline models

class AnalystOutput(BaseModel):
    merchant_vs_peers: str
    cohort_math: str
    urgency_assessment: Literal["SEND_NOW", "DEFER", "SKIP"]
    best_compulsion_lever: str
    contrarian_flag: Optional[str]
    tone_override: Optional[str]
    opportunity_score: float


class StrategyOutput(BaseModel):
    send: bool
    skip_reason: Optional[str] = None
    angle: str
    lever: str
    secondary_levers: list[str] = []
    cta_type: str
    tone: str
    key_numbers_to_include: list[str]
    what_to_avoid: list[str]
    send_as: Literal["vera", "merchant_on_behalf"]
    rationale_for_judge: str


class ComposerOutput(BaseModel):
    body: str
    template_params: list[str]
    cta: str


class ClassifierOutput(BaseModel):
    intent: Literal[
        "AUTO_REPLY",
        "EXPLICIT_YES",
        "EXPLICIT_NO",
        "HOSTILE",
        "QUESTION",
        "SOFT_ENGAGE",
        "UNRELATED",
    ]
    confidence: float
    notes: str

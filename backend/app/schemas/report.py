from datetime import date, datetime
from pydantic import BaseModel, Field

from app.schemas.metrics import FunnelEventSummary, MetricDelta, MetricPoint
from app.schemas.recommendation import Finding, Recommendation


class ReportRunRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None


class ReportSummary(BaseModel):
    id: str
    created_at: datetime
    date_range: str
    status: str
    finding_count: int
    source_timestamps: dict[str, datetime]
    warning: str | None = None


class ReportDetail(ReportSummary):
    metrics: list[MetricPoint] = Field(default_factory=list)
    comparison: list[MetricDelta] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    funnel: FunnelEventSummary | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    report_id: str | None = None


class ChatAnswer(BaseModel):
    answer: str
    evidence_ids: list[str]
    report_id: str

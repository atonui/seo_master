from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    date: date
    metric: str
    value: float
    weight: float = 1.0


class MetricDelta(BaseModel):
    metric: str
    current_value: float
    previous_value: float
    absolute_change: float
    percent_change: float | None
    status: Literal["comparable", "no_baseline"]


class ReportingSettings(BaseModel):
    site_url: str | None = None
    search_console_site: str | None = None
    ga4_property_id: str | None = None
    cta_event: str | None = None
    invite_submit_event: str | None = None


class FunnelEventSummary(BaseModel):
    cta_clicks: int | None
    invite_submissions: int | None
    status: Literal["ready", "setup_needed", "incomplete"]
    warning: str | None = None


class ReportingSettingsUpdate(BaseModel):
    site_url: str | None = Field(default=None, max_length=512)
    search_console_site: str | None = None
    ga4_property_id: str | None = None
    cta_event: str | None = Field(default=None, max_length=100)
    invite_submit_event: str | None = Field(default=None, max_length=100)

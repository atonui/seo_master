from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class SearchConsoleProperty(BaseModel):
    site_url: str
    permission_level: str


class GA4Property(BaseModel):
    property_id: str
    display_name: str
    account_name: str | None = None


class PropertyListResult(BaseModel):
    search_console: list[SearchConsoleProperty] = Field(default_factory=list)
    ga4: list[GA4Property] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PropertySelection(BaseModel):
    search_console_site: str | None = None
    ga4_property_id: str | None = None


class SearchRow(BaseModel):
    date: date
    query: str | None = None
    page: str | None = None
    clicks: int
    impressions: int
    ctr: float
    position: float
    is_aggregate: bool = False


class GA4Row(BaseModel):
    date: date
    landing_page: str | None = None
    session_source_medium: str | None = None
    event_name: str | None = None
    sessions: int = 0
    engagement_rate: float = 0.0
    event_count: int = 0


T = TypeVar("T")


class ConnectorResult(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: T
    retrieved_at: datetime
    complete: bool
    warning: str | None = None
    error_code: str | None = None

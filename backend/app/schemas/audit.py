from datetime import datetime

from pydantic import BaseModel, Field


class PageAudit(BaseModel):
    url: str
    status_code: int | None
    title: str | None = None
    description: str | None = None
    canonical: str | None = None
    robots: str = "index,follow"
    indexable: bool = True
    h1_count: int = 0
    internal_link_count: int = 0
    external_link_count: int = 0
    broken_links: list[str] = Field(default_factory=list)
    issue_codes: list[str] = Field(default_factory=list)


class CrawlResult(BaseModel):
    pages: list[PageAudit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    complete: bool
    retrieved_at: datetime
    request_count: int = 0

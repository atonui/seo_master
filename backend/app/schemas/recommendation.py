from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    metric: str
    value: int | float | str | bool | None
    period: str
    source: str
    label: str | None = None


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    summary: str
    source: str
    evidence: list[Evidence] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)


class RecommendationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_code: str
    evidence_ids: list[str] = Field(min_length=1)
    suggested_action: str = Field(min_length=1, max_length=600)
    measurement: str = Field(min_length=1, max_length=300)
    confidence: Literal["high", "medium", "low"]
    limitations: list[str] = Field(default_factory=list)


class RecommendationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[RecommendationDraft]


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding: Finding
    evidence: list[Evidence] = Field(min_length=1)
    suggested_action: str = Field(min_length=1, max_length=600)
    measurement: str = Field(min_length=1, max_length=300)
    confidence: Literal["high", "medium", "low"]
    limitations: list[str] = Field(default_factory=list)

    def validate_evidence(self, findings: list[Finding]) -> None:
        source = next((finding for finding in findings if finding == self.finding), None)
        if source is None:
            raise ValueError("recommendation refers to an unknown finding")
        allowed = {item.id: item for item in source.evidence}
        if not self.evidence or any(item.id not in allowed or item != allowed[item.id] for item in self.evidence):
            raise ValueError("recommendation evidence must match supplied finding evidence")


def materialize_recommendation(draft: RecommendationDraft, findings: list[Finding]) -> Recommendation:
    if len(set(draft.evidence_ids)) != len(draft.evidence_ids):
        raise ValueError("model returned duplicate evidence IDs")
    candidates = [finding for finding in findings if finding.code == draft.finding_code and set(draft.evidence_ids).issubset({item.id for item in finding.evidence})]
    if len(candidates) != 1:
        raise ValueError("model returned evidence that does not identify exactly one supplied finding")
    source = candidates[0]
    evidence_by_id = {item.id: item for item in source.evidence}
    result = Recommendation(
        finding=source,
        evidence=[evidence_by_id[item] for item in draft.evidence_ids],
        suggested_action=draft.suggested_action,
        measurement=draft.measurement,
        confidence=draft.confidence,
        limitations=list(dict.fromkeys(source.limitations + draft.limitations)),
    )
    result.validate_evidence(findings)
    return result

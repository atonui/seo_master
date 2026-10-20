from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.recommendation import Evidence, Finding, Recommendation, RecommendationBatch, RecommendationDraft
from app.core.config import Settings
from app.services import recommendation_generator


def finding():
    return Finding(
        code="search_low_ctr", title="Low click-through rate", summary="Query receives impressions with low CTR.",
        source="search_console", evidence=[Evidence(id="gsc:q1:impressions", metric="impressions", value=1200, period="2026-10-01", source="Google Search Console", label="used tractor parts")],
        limitations=["One day of data"],
    )


def test_recommendation_requires_metric_evidence():
    with pytest.raises(ValueError):
        Recommendation(finding=finding(), evidence=[], suggested_action="Review snippet copy.", measurement="CTR", confidence="medium", limitations=[])


def test_recommendation_rejects_unobserved_evidence_id():
    rec = Recommendation(finding=finding(), evidence=[Evidence(id="invented", metric="CTR", value=0.0, period="today", source="model")], suggested_action="Review snippet copy.", measurement="CTR", confidence="medium", limitations=[])
    with pytest.raises(ValueError):
        rec.validate_evidence([finding()])


def test_schema_rejects_missing_evidence_ids():
    with pytest.raises(ValidationError):
        RecommendationDraft.model_validate({"finding_code":"search_low_ctr", "suggested_action":"Change title", "measurement":"CTR", "confidence":"medium", "limitations":[]})


def test_recommendations_include_metric_evidence(monkeypatch):
    class Responses:
        def parse(self, **kwargs):
            assert kwargs["model"] == "test-model"
            return type("Response", (), {"output_parsed": RecommendationBatch(recommendations=[RecommendationDraft(
                finding_code="search_low_ctr", evidence_ids=["gsc:q1:impressions"],
                suggested_action="Review the page title and description for this query.", measurement="Query CTR over the next 28 days",
                confidence="medium", limitations=[],
            )])})()

    class MockClient:
        responses = Responses()

    monkeypatch.setattr(recommendation_generator, "get_settings", lambda: Settings(openai_api_key="test-key", openai_model="test-model"))
    monkeypatch.setattr(recommendation_generator, "OpenAI", lambda **kwargs: MockClient())
    result = recommendation_generator.generate_recommendations([finding()])
    assert result[0].evidence[0].value == 1200


def test_model_output_rejects_missing_evidence(monkeypatch):
    class Responses:
        def parse(self, **kwargs):
            return type("Response", (), {"output_parsed": RecommendationBatch(recommendations=[RecommendationDraft(
                finding_code="search_low_ctr", evidence_ids=["unknown"], suggested_action="Make a change",
                measurement="CTR", confidence="low", limitations=[],
            )])})()

    class MockClient:
        responses = Responses()

    monkeypatch.setattr(recommendation_generator, "get_settings", lambda: Settings(openai_api_key="test-key"))
    monkeypatch.setattr(recommendation_generator, "OpenAI", lambda **kwargs: MockClient())
    with pytest.raises(ValueError, match="evidence"):
        recommendation_generator.generate_recommendations([finding()])


def test_same_type_findings_are_tied_to_each_query(monkeypatch):
    first = finding()
    second = first.model_copy(update={"evidence": [first.evidence[0].model_copy(update={"id": "gsc:q2:impressions", "label": "alternator parts"})]})
    class Responses:
        def parse(self, **kwargs):
            return type("Response", (), {"output_parsed": RecommendationBatch(recommendations=[
                RecommendationDraft(finding_code="search_low_ctr", evidence_ids=["gsc:q1:impressions"], suggested_action="Review one snippet.", measurement="CTR", confidence="low", limitations=[]),
                RecommendationDraft(finding_code="search_low_ctr", evidence_ids=["gsc:q2:impressions"], suggested_action="Review the other snippet.", measurement="CTR", confidence="low", limitations=[]),
            ])})()
    class MockClient:
        responses = Responses()
    monkeypatch.setattr(recommendation_generator, "get_settings", lambda: Settings(openai_api_key="test-key"))
    monkeypatch.setattr(recommendation_generator, "OpenAI", lambda **kwargs: MockClient())
    results = recommendation_generator.generate_recommendations([first, second])
    assert [result.finding.evidence[0].label for result in results] == ["used tractor parts", "alternator parts"]

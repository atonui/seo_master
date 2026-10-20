from pydantic import BaseModel, ConfigDict, Field


class ChatDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(min_length=1)

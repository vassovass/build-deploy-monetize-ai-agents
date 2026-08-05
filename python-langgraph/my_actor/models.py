"""Module defines Pydantic models for this project.

Two contracts live here, deliberately split:
- `ScrapedPost` validates raw apify/instagram-scraper items (field aliases, constraints).
- `InstagramPost` is the LLM-facing output shape (plain, constraint-free fields).
Keeping them separate stops scraper-internal names and JSON-schema constraint keywords
from leaking into the structured-output schema the LLM sees - OpenAI's strict
structured-output subset rejects keywords like `minimum` and `minLength`.

Resources:
- https://docs.pydantic.dev/latest/concepts/models/
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - needed at runtime by pydantic
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ScrapedPost(BaseModel):
    """Validates a raw apify/instagram-scraper dataset item.

    This model is the single source of truth for which posts count toward the totals:
    missing fields, malformed URLs or timestamps, and Instagram's -1 sentinel for hidden
    like/comment counts all fail validation and the post is skipped, while genuine zero
    counts pass.
    """

    model_config = ConfigDict(populate_by_name=True)

    url: HttpUrl
    likes: int = Field(ge=0, validation_alias='likesCount')
    comments: int = Field(ge=0, validation_alias='commentsCount')
    timestamp: datetime
    caption: str | None = None
    alt: str | None = None


class InstagramPost(BaseModel):
    """A post as it appears in the agent's structured answer.

    Fields stay plain and constraint-free on purpose: this model is embedded in the
    JSON schema sent to the LLM, which must not carry validation aliases or constraint
    keywords (see the module docstring).
    """

    url: str
    likes: int
    comments: int
    timestamp: str
    caption: str | None = None
    alt: str | None = None


class AgentStructuredOutput(BaseModel):
    """Structured output returned by the ReAct agent."""

    total_likes: int
    total_comments: int
    most_popular_posts: list[InstagramPost] = Field(
        default_factory=list,
        description=(
            'The top post(s) by engagement, always as an array - use a single-element array '
            'when the query asks for only the most popular post, and an empty array when the '
            'query does not ask for one.'
        ),
    )

    @field_validator('most_popular_posts', mode='before')
    @classmethod
    def _coerce_to_list(cls, value: Any) -> Any:
        """The LLM sometimes returns null, a bare object, or nulls inside the list.

        Coercing here avoids a structured-output retry round-trip; the trade-off is that
        main.py must treat an empty list as a first-class outcome, which it does (the
        completeness check and billing are keyed to the deterministic scrape cache, not
        to this field).
        """
        if value is None:
            return []
        if isinstance(value, (dict, InstagramPost)):
            return [value]
        if isinstance(value, list):
            return [item for item in value if item is not None]
        return value

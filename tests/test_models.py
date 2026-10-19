from uuid import uuid4

import pytest
from pydantic import ValidationError

from customer_needs_agent.models import (
    AnalysisResponse,
    AnalysisStatus,
    Budget,
    Requirements,
)


def test_budget_rejects_inverted_range() -> None:
    with pytest.raises(ValidationError):
        Budget(min=100, max=10)


def test_completed_response_requires_recommendation() -> None:
    with pytest.raises(ValidationError):
        AnalysisResponse(
            conversation_id=uuid4(),
            status=AnalysisStatus.COMPLETED,
            requirements=Requirements(),
        )


def test_clarification_response_rejects_recommendations_without_question() -> None:
    with pytest.raises(ValidationError):
        AnalysisResponse(
            conversation_id=uuid4(),
            status=AnalysisStatus.NEEDS_CLARIFICATION,
            requirements=Requirements(),
        )

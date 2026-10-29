
from pydantic import ConfigDict

from app.schemas.resource import ResourceResponse


class SemanticSearchResult(ResourceResponse):
    model_config = ConfigDict(from_attributes=True)

    similarity_score: float

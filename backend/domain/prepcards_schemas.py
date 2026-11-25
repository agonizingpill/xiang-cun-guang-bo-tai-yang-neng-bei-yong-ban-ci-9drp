from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class PrepareCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    airslot: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    meter: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class IssueCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class ClaimCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    receipt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    clear: bool

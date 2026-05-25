from pydantic import BaseModel, Field

from typing import List


class Reflection(BaseModel):

    missing: str = Field(
        description="Critique of what is missing in the answer."
    )

    unnecessary: str = Field(
        description="Critique of what is unnecessary in the answer."
    )


class AnswerQuestion(BaseModel):

    answer: str = Field(
        description="Detailed answer to the user's question."
    )

    reflection: Reflection = Field(
        description="Self-reflection and critique of the answer."
    )

    search_queries: List[str] = Field(
        description="Search queries for improving the answer."
    )
from schemas.models import AnswerQuestion


def build_responder(llm):

    structured_llm = llm.with_structured_output(
        AnswerQuestion
    )

    return structured_llm
from langchain_core.prompts import ChatPromptTemplate

from prompts.prompts import REVISOR_PROMPT


def build_revisor_chain(llm):

    prompt = ChatPromptTemplate.from_template(
        REVISOR_PROMPT
    )

    return prompt | llm
from typing import TypedDict, List

from langgraph.graph import StateGraph, END


class AgentState(TypedDict):

    question: str

    initial_response: object

    search_results: List

    final_response: str


def build_graph(
    responder,
    tavily_tool,
    revisor_chain
):

    workflow = StateGraph(AgentState)

    # -----------------------------------
    # RESPONDER NODE
    # -----------------------------------

    def responder_node(state):

        response = responder.invoke(
            state["question"]
        )

        return {
            "initial_response": response
        }

    # -----------------------------------
    # SEARCH NODE
    # -----------------------------------

    def search_node(state):

        response = state["initial_response"]

        all_search_results = []

        for query in response.search_queries:

            results = tavily_tool.invoke(query)

            all_search_results.append(results)

        return {
            "search_results": all_search_results
        }

    # -----------------------------------
    # REVISOR NODE
    # -----------------------------------

    def revisor_node(state):

        response = state["initial_response"]

        final_response = revisor_chain.invoke({

            "original_answer": response.answer,

            "missing": response.reflection.missing,

            "unnecessary": response.reflection.unnecessary,

            "search_results": state["search_results"]
        })

        return {
            "final_response": final_response.content
        }

    # -----------------------------------
    # ADD NODES
    # -----------------------------------

    workflow.add_node(
        "responder",
        responder_node
    )

    workflow.add_node(
        "search",
        search_node
    )

    workflow.add_node(
        "revisor",
        revisor_node
    )

    # -----------------------------------
    # ADD EDGES
    # -----------------------------------

    workflow.set_entry_point(
        "responder"
    )

    workflow.add_edge(
        "responder",
        "search"
    )

    workflow.add_edge(
        "search",
        "revisor"
    )

    workflow.add_edge(
        "revisor",
        END
    )

    return workflow.compile()
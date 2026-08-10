from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from core.config import llm
from core.prompts import SEARCH_PROMPT
from core.utils import AgentState, route_tools, search_food_tool

tools = [search_food_tool]
llm_with_tools = llm.bind_tools(tools)

def food_search_node(state: AgentState):
    print(" ↳ 🔍 [Search Agent] Querying the database...")
    messages = [SystemMessage(content=SEARCH_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

workflow = StateGraph(AgentState)
workflow.add_node("food_search", food_search_node)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "food_search")
workflow.add_conditional_edges("food_search", route_tools, {"tools": "tools", "__end__": END})
workflow.add_edge("tools", "food_search")

app = workflow.compile()

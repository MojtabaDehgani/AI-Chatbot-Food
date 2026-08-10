from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from core.config import llm
from core.prompts import GENERATE_RECOMMENDATION_NODE_PROMPT
from core.utils import AgentState, route_tools, search_food_tool

tools = [search_food_tool]
llm_with_tools = llm.bind_tools(tools)

def food_suggestion_node(state: AgentState):
    print(" ↳ 🍕 [Suggest Agent] Brainstorming and recommending...")
    messages = [SystemMessage(content=GENERATE_RECOMMENDATION_NODE_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

workflow = StateGraph(AgentState)
workflow.add_node("food_suggestion", food_suggestion_node)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "food_suggestion")
workflow.add_conditional_edges("food_suggestion", route_tools, {"tools": "tools", "__end__": END})
workflow.add_edge("tools", "food_suggestion")

app = workflow.compile()

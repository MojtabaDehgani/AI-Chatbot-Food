from langgraph.graph.message import add_messages
from typing import Annotated, Literal
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langchain_core.tools import tool
from database import db_manager

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

def route_tools(state: AgentState) -> Literal["tools", "__end__"]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "__end__"

@tool
def search_food_tool(food_name: str = None, restaurant_name: str = None) -> str:
    """Search for foods in restaurants based on food name, restaurant name, or both."""
    try:
        results = db_manager.food_search(food_name=food_name, restaurant_name=restaurant_name)
        if not results:
            return "No matching food or restaurant found in the database."
        
        formatted_results = []
        for r in results:
            formatted_results.append(f"Food: {r['food_name']} | Restaurant: {r['restaurant_name']} | Category: {r['food_category']} | Price: {r['price']}")
        return "\n".join(formatted_results)
    except Exception as e:
        return f"Database error while searching for food: {e}"

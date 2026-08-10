from langgraph.graph.message import add_messages
from typing import Annotated, Literal
from typing_extensions import TypedDict
from langchain_core.messages import SystemMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from core.config import llm
from database import db_manager
from core.prompts import CHATBOT_PROMPT


@tool
def check_order_status_tool(order_id: int) -> str:
    """Check the current status of an order using its order ID."""
    return str(db_manager.check_order_status(order_id))

@tool
def comment_order_tool(order_id: int, person_name: str, comment: str) -> str:
    """Add or update a comment/review for a specific order."""
    return str(db_manager.comment_order(order_id, person_name, comment))

@tool
def cancel_order_tool(order_id: int, phone_number: str) -> str:
    """Cancel an existing order. Requires BOTH the order ID and the user's phone number."""
    return str(db_manager.cancel_order(order_id, phone_number))

@tool
def create_order_tool(person_name: str, phone_number: str, order_description: str) -> str:
    """Create a new food order. Requires user's name, phone number, and a description of their order."""
    return str(db_manager.create_order(person_name, phone_number, order_description))

@tool
def get_user_orders_tool(phone_number: str) -> str:
    """Retrieve a list of all past and current orders for a specific user using their phone number."""
    return str(db_manager.get_all_user_orders(phone_number))

normal_tools = [check_order_status_tool, comment_order_tool, create_order_tool, get_user_orders_tool]
sensitive_tools = [cancel_order_tool]
all_tools = normal_tools + sensitive_tools

class OrderState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages] 
    user_info: dict 

llm_with_tools = llm.bind_tools(all_tools)

def assistant_node(state: OrderState):
    print(" ↳ 🤖 [Order Agent] Thinking...")
    
    u_info = state.get("user_info", {})
    name = u_info.get("name", "Unknown")
    phone = u_info.get("phone", "Unknown")
    
    dynamic_prompt = (
        f"{CHATBOT_PROMPT}\n\n"
        f"CRITICAL SYSTEM NOTE: The current authenticated user is {name} with phone number {phone}. "
        "Use this information silently and directly for your tools. NEVER ask the user for their phone number or name to cancel or create an order, because you already have it securely injected!\n\n"
        "🚨 STRICT LOGIC RULE: Before calling create_order_tool, you MUST review the chat history. "
        "If the user is trying to order a food item that the system previously stated as 'not found', 'couldn't find', or unavailable, "
        "you MUST NOT create the order! Instead, apologize and tell the user that you cannot order unavailable items.\n\n"
        "🚨 FORMATTING RULE FOR DATABASE: When calling create_order_tool, you MUST format the order description CLEANLY as '[Food Name] from [Restaurant Name]'. "
        "STRIP and REMOVE any articles, numbers, or quantities such as 'a ', 'an ', 'the ', or '1x ' from the beginning of the food name.\n\n"
        "🚨 FORMATTING RULE FOR ORDER HISTORY: If the user asks for their order history or all their orders, call get_user_orders_tool. "
        "If orders are found, you MUST format the final response as a Markdown table with exactly three columns: | Order ID | Order Description | Status |.\n\n" # <--- این قانون جدید برای رسم جدول
        "🚨 POST-ACTION RULE: Once a tool returns a success message, you MUST inform the user EXACTLY ONCE. "
        "Summarize the result naturally. DO NOT repeat the exact same sentence multiple times."
    )
    
    messages = [SystemMessage(content=dynamic_prompt)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def route_tools(state: OrderState) -> Literal["normal_tools", "sensitive_tools", "__end__"]:
    last_message = state["messages"][-1]
    
    if not last_message.tool_calls:
        return "__end__"
    
    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "cancel_order_tool":
            print(" ↳ ⚠️ [Router] Sensitive tool detected! Routing to sensitive_tools node.")
            return "sensitive_tools"
            
    print(" ↳ 🛠️ [Router] Normal tool detected. Routing to normal_tools node.")
    return "normal_tools"

workflow = StateGraph(OrderState)

workflow.add_node("assistant", assistant_node)
workflow.add_node("normal_tools", ToolNode(normal_tools))
workflow.add_node("sensitive_tools", ToolNode(sensitive_tools)) 

workflow.add_edge(START, "assistant")

workflow.add_conditional_edges(
    "assistant",
    route_tools,
    {
        "normal_tools": "normal_tools",
        "sensitive_tools": "sensitive_tools",
        "__end__": END
    }
)

workflow.add_edge("normal_tools", "assistant")
workflow.add_edge("sensitive_tools", "assistant")

memory = MemorySaver()

app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["sensitive_tools"] 
)

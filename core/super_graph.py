from typing import Annotated, TypedDict, Literal
from langchain_core.messages import AnyMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables.config import RunnableConfig
from core.config import llm
from core.prompts import PRIMARY_ASSISTANT_PROMPT , RESPOND_NODE_PROMPT
from agents.doc_retrieval import app as doc_retrieval_app
from agents.suggest_food import app as suggest_food_app
from agents.search_food import app as search_food_app
from agents.order_management import app as order_management_app
from langchain_core.messages import RemoveMessage, HumanMessage
from langgraph.graph.message import add_messages
import re


def path_reducer(left: list[str], right: list[str]):
    if right and right[0] == "CLEAR":
        return right[1:]
    return left + right

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_info: dict
    summary: str
    current_skill: str 
    path: Annotated[list[str], path_reducer]

def fetch_user_info(state: State, config: RunnableConfig): 
    print("👤 [System] Fetching real user info from session...")
    configurable = config.get("configurable", {})
    real_name = configurable.get("user_name", "Unknown User")
    real_phone = configurable.get("user_phone", "Unknown Phone")
    real_user_data = {"name": real_name, "phone": real_phone}
    return {"user_info": real_user_data, "path": ["CLEAR", "fetch_user_info"]}

def summarize_conversation(state: State):
    messages = state.get("messages", [])
    summary = state.get("summary", "")
    if len(messages) <= 8: 
        return {"path": ["summarize_conversation"]}
        
    print("📝 [System] Conversation is getting long. Summarizing to save tokens...")
    messages_to_summarize = messages[:-4]
    
    prompt = (
        f"Here is the summary of the conversation so far: {summary}\n\n"
        "Extend the summary by taking into account the new messages above. "
        "Include any details that might be relevant for a food ordering assistant (preferences, names, issues). "
        "Keep it concise."
    )
    
    summary_query = messages_to_summarize + [HumanMessage(content=prompt)]
    response = llm.invoke(summary_query)
    new_summary = response.content
    delete_messages = [RemoveMessage(id=m.id) for m in messages_to_summarize]
    
    return {
        "summary": new_summary,
        "messages": delete_messages, 
        "path": ["summarize_conversation"]
    }

class RouteDecision(BaseModel):
    route: Literal["direct_response", "doc_retrieval", "suggest_food", "search_food", "order_management"] = Field(
        description="Select the appropriate route based on the user's request."
    )

llm_router = llm.with_structured_output(RouteDecision)

def primary_assistant(state: State):
    print("🧠 [Manager] Routing your request...")
    messages = state.get("messages", [])
    summary = state.get("summary", "")

    last_msg = messages[-1].content if messages else ""
    last_msg_lower = last_msg.lower()
    
    last_ai_msg = ""
    if len(messages) >= 2:
        last_ai_msg = str(messages[-2].content).lower()
    
    system_content = PRIMARY_ASSISTANT_PROMPT
    if summary:
        system_content += f"\n\n[Previous Conversation Summary]: {summary}"
        
    system_content += (
        "\n\nCRITICAL ROUTING INSTRUCTIONS - FOLLOW EXACTLY:\n"
        "1. 'order_management': The user is placing an order, confirming ('order it', 'yes'), canceling, OR answering a clarification question about what to order.\n"
        "2. 'search_food': The user is looking for a specific food (e.g., 'I want a pizza', 'Do you have burgers?').\n"
        "3. 'suggest_food': The user wants recommendations (e.g., 'I am hungry', 'What do you suggest?').\n"
        "4. 'doc_retrieval': The user asks for facts, history, or nutrition.\n"
        "5. 'direct_response': ONLY for greetings (e.g., 'hi') or completely unrelated chat.\n\n"
        "NEVER route food names (Pizza, Burger) or order answers to 'direct_response'."
    )

    messages_to_run = [SystemMessage(content=system_content)] + messages
    decision = llm_router.invoke(messages_to_run)
    route = decision.route

    if any(phrase in last_msg_lower for phrase in ["cancel", "order it", "order that", "my orders", "all orders", "order history"]):
        route = "order_management"

    elif any(word in last_msg_lower for word in ["pizza", "burger", "eat"]) and route == "direct_response":
        route = "order_management"

    elif last_msg_lower.replace(" ", "").isdigit():
        print(" ↳ 🛡️ [Context Guard] User sent digits. Routing to order_management.")
        route = "order_management"

    elif route == "direct_response" and any(re.search(rf"\b{word}\b", last_ai_msg) for word in ["id", "cancel", "clarify", "provide", "number", "phone"]):
        print(" ↳ 🛡️ [Context Guard] User is answering a previous question about an order/ID.")
        route = "order_management"

    print(f" ↳ 🚦 LLM chose: {decision.route} | Final Route applied: {route}")
    return {"current_skill": route, "path": ["primary_assistant"]}

def primary_assistant_tools(state: State):
    print(" ↳ 👋 [Skill] Direct Response / General Chat")
    messages = state.get("messages", [])
    summary = state.get("summary", "")
    system_content = RESPOND_NODE_PROMPT
    if summary:
        system_content += (
            f"\n\n[Previous Conversation Summary]:\n{summary}\n"
            "Use this summary to remember user preferences and past context."
        )
    sys_msg = SystemMessage(content=system_content)
    messages_to_run = [sys_msg] + messages
    response = llm.invoke(messages_to_run)
    return {"messages": [AIMessage(content=response.content)], "path": ["primary_assistant_tools"]}

def enter_doc_retrieval(state: State, config: RunnableConfig):
    print(" ↳ 📚 Executing: Doc Retrieval Sub-graph")
    result = doc_retrieval_app.invoke({"messages": state["messages"]}, config)
    return {"messages": [result["messages"][-1]], "path": ["enter_doc_retrieval"]}

def enter_suggestion_food(state: State, config: RunnableConfig):
    print(" ↳ 🍕 Executing: Suggest Food Sub-graph")
    result = suggest_food_app.invoke({"messages": state["messages"]}, config)
    return {"messages": [result["messages"][-1]], "path": ["enter_suggestion_food"]}

def enter_search_food(state: State, config: RunnableConfig):
    print(" ↳ 🔍 Executing: Search Food Sub-graph")
    result = search_food_app.invoke({"messages": state["messages"]}, config)
    return {"messages": [result["messages"][-1]], "path": ["enter_search_food"]}


def enter_order_management(state: State, config: RunnableConfig):
    print(" ↳ 📦 Executing: Order Management Sub-graph")
    
    base_thread_id = config.get("configurable", {}).get("thread_id", "default")
    sub_config = {
        "configurable": {
            "thread_id": f"{base_thread_id}_order", 
            "user_name": config.get("configurable", {}).get("user_name", ""),
            "user_phone": config.get("configurable", {}).get("user_phone", "")
        }
    }
    
    result = order_management_app.invoke({
        "messages": state["messages"], 
        "user_info": state.get("user_info", {})
    }, config=sub_config) 
    
    return {"messages": [result["messages"][-1]], "path": ["enter_order_management"]}


def leave_skill(state: State):
    print("✅ [System] Leaving skill, cleaning up state, and preparing for end...")
    return {"current_skill": "direct_response", "path": ["leave_skill"]}

def route_after_skill(state: State) -> Literal["primary_assistant_tools", "__end__"]:
    last_message = state["messages"][-1]
    
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "__end__"
        
    content = last_message.content
    if not content or "Error" in content:
        print(" ↳ ⚠️ [Router] Sub-graph returned an error or empty message. Falling back to Assistant.")
        return "primary_assistant_tools"
    print(" ↳ 🏁 [Router] Sub-graph execution successful. Ending graph.")
    return "__end__"

def route_after_assistant(state: State):
    return state["current_skill"]

workflow = StateGraph(State)

workflow.add_node("fetch_user_info", fetch_user_info)
workflow.add_node("summarize_conversation", summarize_conversation)
workflow.add_node("primary_assistant", primary_assistant)
workflow.add_node("primary_assistant_tools", primary_assistant_tools)

workflow.add_node("enter_doc_retrieval", enter_doc_retrieval)
workflow.add_node("enter_suggestion_food", enter_suggestion_food)
workflow.add_node("enter_search_food", enter_search_food)
workflow.add_node("enter_order_management", enter_order_management)
workflow.add_node("leave_skill", leave_skill)

workflow.add_edge(START, "fetch_user_info")
workflow.add_edge("fetch_user_info", "summarize_conversation")
workflow.add_edge("summarize_conversation", "primary_assistant")

workflow.add_conditional_edges(
    "primary_assistant",
    route_after_assistant,
    {
        "direct_response": "primary_assistant_tools",
        "doc_retrieval": "enter_doc_retrieval",
        "suggest_food": "enter_suggestion_food",
        "search_food": "enter_search_food",
        "order_management": "enter_order_management"
    }
)

workflow.add_edge("enter_doc_retrieval", "leave_skill")
workflow.add_edge("enter_suggestion_food", "leave_skill")
workflow.add_edge("enter_search_food", "leave_skill")
workflow.add_edge("enter_order_management", "leave_skill")
workflow.add_edge("primary_assistant_tools", END)

workflow.add_conditional_edges(
    "leave_skill",
    route_after_skill,
    {
        "primary_assistant_tools": "primary_assistant_tools", 
        "__end__": END
    }
)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

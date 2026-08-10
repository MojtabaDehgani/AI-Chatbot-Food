import uuid
import chainlit as cl
from langchain_core.messages import HumanMessage
from core.super_graph import app as super_app 
from core.prompts import WELCOME_MESSAGE_START
from langchain_community.callbacks import get_openai_callback
import logging
from agents.order_management import app as order_management_app
from database.db_manager import verify_user
from langchain_core.messages import HumanMessage, ToolMessage

logging.getLogger("duckduckgo_search").setLevel(logging.CRITICAL)

@cl.on_chat_start
async def start():
    thread_id = str(uuid.uuid4())
    cl.user_session.set("config", {"configurable": {"thread_id": thread_id}})
    cl.user_session.set("is_authenticated", False) 
    
    await cl.Message(content=WELCOME_MESSAGE_START).send()

@cl.action_callback("confirm_cancellation")
async def on_action(action: cl.Action):
    await action.remove()
    config = cl.user_session.get("config")

    base_thread_id = config["configurable"]["thread_id"]
    sub_config = {
        "configurable": {
            "thread_id": f"{base_thread_id}_order",
            "user_name": config.get("configurable", {}).get("user_name", ""),
            "user_phone": config.get("configurable", {}).get("user_phone", "")
        }
    }

    if action.value == "yes":
        await cl.Message(content="⏳ **Processing Cancellation...**").send()

        with get_openai_callback() as cb:
            result = await cl.make_async(order_management_app.invoke)(None, config=sub_config)

        tool_msg = result["messages"][-2]
        final_ai_msg = result["messages"][-1]

        super_app.update_state(config, {"messages": [tool_msg, final_ai_msg]})

        await cl.Message(content=final_ai_msg.content).send()

    else:
        await cl.Message(content="❌ **Cancellation aborted.** Your order is safe!").send()
        
        order_state = order_management_app.get_state(sub_config)
        last_msg = order_state.values.get("messages", [])[-1]
        
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            tool_call_id = last_msg.tool_calls[0]["id"]
            tool_name = last_msg.tool_calls[0]["name"]
            
            abort_tool_msg = ToolMessage(
                content="User chose to abort cancellation. Tell the user the order is safe.",
                tool_call_id=tool_call_id,
                name=tool_name
            )
            
            order_management_app.update_state(
                sub_config, 
                {"messages": [abort_tool_msg]}, 
                as_node="sensitive_tools"
            )
            
            result = await cl.make_async(order_management_app.invoke)(None, config=sub_config)
            final_ai_msg = result["messages"][-1]
            
            super_app.update_state(config, {"messages": [abort_tool_msg, final_ai_msg]})
            await cl.Message(content=final_ai_msg.content).send()

        
@cl.on_message
async def main(message: cl.Message):
    user_input = message.content
    config = cl.user_session.get("config")
    is_auth = cl.user_session.get("is_authenticated")

    if not is_auth:
        try:
            name, phone = [part.strip() for part in user_input.split(',')]
            
            if verify_user(name, phone):
                cl.user_session.set("is_authenticated", True)
                
                config["configurable"]["user_name"] = name
                config["configurable"]["user_phone"] = phone
                cl.user_session.set("config", config)
                
                await cl.Message(content=f"✅ Authentication was successful.\nWelcome {name} !\nHow can I help you today?").send()
            else:
                await cl.Message(content="❌ **Authentication Failed!**\nUser not found or incorrect phone number. Please check your details and try again.").send()
                
        except ValueError:
            await cl.Message(content="⚠️ **Invalid format!**\nPlease make sure to separate your name and phone number with a comma (,).\nExample: `First Name, 09XXXXXXXXX`").send()
        return

    async with cl.Step(name="Analyzing your request...") as step:
        try:
            inputs = {"messages": [HumanMessage(content=user_input)]}
            
            with get_openai_callback() as cb:
                result = await cl.make_async(super_app.invoke)(inputs, config=config)
            
            token_info = (
                f"📊 **Token Usage:** Total ({cb.total_tokens}) | "
                f"Input ({cb.prompt_tokens}) | "
                f"Output ({cb.completion_tokens})"
            )
            
            execution_path = result.get("path", [])
            path_visual = " ➔ ".join([f"`{node}`" for node in execution_path])

            if "enter_suggestion_food" in execution_path or "enter_search_food" in execution_path:
                step.name = "Smart Food Recommendation"
                intro_text = "Searching the database and analyzing options..."
            elif "enter_order_management" in execution_path:
                step.name = "Customer Service"
                intro_text = "Checking order management systems..."
            elif "enter_doc_retrieval" in execution_path:
                step.name = "General & Nutritional Information"
                intro_text = "Scanning knowledge base..."
            else:
                step.name = "General Conversation"
                intro_text = "Processing response..."

            step.output = f"{intro_text}\n\n🗺️ **Graph Execution Route:**\n{path_visual}\n\n{token_info}"

            base_thread_id = config["configurable"]["thread_id"]
            sub_config = {
                "configurable": {
                    "thread_id": f"{base_thread_id}_order",
                    "user_name": config.get("configurable", {}).get("user_name", ""),
                    "user_phone": config.get("configurable", {}).get("user_phone", "")
                }
            }
            
            order_state = order_management_app.get_state(sub_config)
            
            if order_state.next and "sensitive_tools" in order_state.next:
                actions = [
                    cl.Action(name="confirm_cancellation", value="yes", label="✅ YES"),
                    cl.Action(name="confirm_cancellation", value="no", label="❌ Cancel", theme="error")
                ]
                await cl.Message(
                    content="⚠️ **Confirmation Required:** Are you sure you want to cancel this order?", 
                    actions=actions
                ).send()
                return 

            final_answer = result["messages"][-1].content
            await cl.Message(content=final_answer).send()

        except Exception as e:
            step.name = "System Error"
            step.output = f"Failed to process the request: {str(e)}"
            step.status = "error"
            await cl.Message(content=f"❌ Error details: {str(e)}").send()
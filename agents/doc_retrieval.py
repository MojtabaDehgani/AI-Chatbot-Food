import json
from langgraph.graph.message import add_messages
from typing import Annotated, List, Literal
from typing_extensions import TypedDict
from langchain_core.messages import SystemMessage, HumanMessage, AnyMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from core.config import llm, get_lancedb_connection, hf_embeddings
from core.prompts import CONTENT_GRADER_PROMPT , GENERATE_PROMPT
from langchain_community.vectorstores import LanceDB
from langchain_community.tools import DuckDuckGoSearchResults

db = get_lancedb_connection()
vector_store = LanceDB(connection=db, table_name="food_knowledge_base", embedding=hf_embeddings)
retriever = vector_store.as_retriever(search_kwargs={"k": 2})
ddg_search = DuckDuckGoSearchResults(max_results=2)

@tool
def doc_retrieval_tool(query: str) -> str:
    """Retrieve documents from the food knowledge base vector store."""
    docs = retriever.invoke(query)
    return "\n\n".join([d.page_content for d in docs])

@tool
def web_search_tool_func(query: str) -> str:
    """Search the web for food and nutrition information."""
    return ddg_search.invoke(query)

llm_with_retrieval = llm.bind_tools([doc_retrieval_tool])
llm_with_web = llm.bind_tools([web_search_tool_func])

class RAGState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    documents: List[str]
    web_fallback: str 

def doc_retrieval(state: RAGState):
    print(" ↳ 📚 [RAG] Agent deciding on document retrieval...")
    
    current_turn = []
    for msg in reversed(state["messages"]):
        current_turn.insert(0, msg)
        if getattr(msg, "type", "") == "human" or type(msg).__name__ == "HumanMessage":
            break
            
    question = current_turn[0].content if current_turn else ""
    
    system_prompt = (
        "You are a retrieval agent. Use the doc_retrieval_tool to fetch information "
        f"STRICTLY based on the user's LATEST question: '{question}'."
    )
    
    messages = [SystemMessage(content=system_prompt)] + current_turn
    response = llm_with_retrieval.invoke(messages)
    return {"messages": [response], "question": question}

def route_doc_retrieval(state: RAGState) -> Literal["doc_retrieval_tools", "enter_filter"]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "doc_retrieval_tools"
    return "enter_filter"

def enter_filter(state: RAGState):
    print(" ↳ ➡️ Entering Filter Phase")
    return {}

def filter_node(state: RAGState):
    print(" ↳ 🧹 Filtering retrieved content (Extracting tool outputs)...")
    docs = []
    for msg in reversed(state["messages"]):
        if getattr(msg, "type", "") == "human" or type(msg).__name__ == "HumanMessage":
            break
        if hasattr(msg, 'name') and msg.name == "doc_retrieval_tool":
            docs.append(msg.content)
    return {"documents": docs}

def enter_content_grader(state: RAGState):
    print(" ↳ ➡️ Entering Content Grader")
    return {}

def content_grader(state: RAGState):
    print(" ↳ ⚖️ Grading document relevance...")
    question = state.get("question", "")
    documents = state.get("documents", [])
    filtered_docs = []
    web_fallback = "No"
        
    for doc in documents:
        if not doc.strip():
            continue
            
        prompt = f"Retrieved document: \n\n {doc} \n\n User question: {question}"
        messages = [SystemMessage(content=CONTENT_GRADER_PROMPT), HumanMessage(content=prompt)]
        response = llm.invoke(messages)
        
        content_lower = response.content.lower()
        
        if '"score": "yes"' in content_lower or '"score":"yes"' in content_lower or "score: yes" in content_lower:
            score = "yes"
        else:
            try:
                parsed = json.loads(response.content.replace("```json", "").replace("```", "").strip())
                score = str(parsed.get("score", "no")).lower()
            except:
                score = "no"
                
        if score == "yes":
            filtered_docs.append(doc)
            
    if not filtered_docs:
        print(" ↳ ⚠️ No relevant docs found! Triggering web search.")
        web_fallback = "Yes"
    else:
        print(" ↳ ✅ Relevant docs found.")
        
    return {"documents": filtered_docs, "web_fallback": web_fallback}

def route_content_grader(state: RAGState) -> Literal["enter_web_search", "enter_generate"]:
    if state.get("web_fallback") == "Yes":
        return "enter_web_search"
    return "enter_generate"

def enter_web_search(state: RAGState):
    print(" ↳ ➡️ Entering Web Search Phase")
    return {}

def web_search(state: RAGState):
    print(" ↳ 🌐 [Web Agent] Deciding on web search...")
    question = state.get("question", "")
    current_turn = []
    for msg in reversed(state["messages"]):
        current_turn.insert(0, msg)
        if getattr(msg, "type", "") == "human" or type(msg).__name__ == "HumanMessage":
            break  
    system_prompt = (
        "You are a precise web search agent. Use the web_search_tool_func to search the internet "
        f"for the exact answer to this question: '{question}'."
    )
    messages = [SystemMessage(content=system_prompt)] + current_turn
    response = llm_with_web.invoke(messages)
    return {"messages": [response]}

def route_web_search(state: RAGState) -> Literal["web_search_tools", "enter_generate"]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "web_search_tools"
    return "enter_generate"

def enter_generate(state: RAGState):
    print(" ↳ ➡️ Entering Generation Phase")
    return {}

def generate(state: RAGState):
    print(" ↳ ✍️ Generating final response...")
    question = state.get("question", "")
    documents = state.get("documents", [])
    
    for msg in reversed(state["messages"]):
        if getattr(msg, "type", "") == "human" or type(msg).__name__ == "HumanMessage":
            break
        if hasattr(msg, 'name') and msg.name == "web_search_tool_func":
            documents.append(msg.content)
            
    docs_str = "\n\n".join(documents)
    
    prompt = f"Context: {docs_str} \n\nQuestion: {question} \nAnswer:"
    messages = [SystemMessage(content=GENERATE_PROMPT), HumanMessage(content=prompt)]
    response = llm.invoke(messages)
    
    return {"messages": [AIMessage(content=response.content)]}

workflow = StateGraph(RAGState)

workflow.add_node("doc_retrieval", doc_retrieval)
workflow.add_node("doc_retrieval_tools", ToolNode([doc_retrieval_tool]))
workflow.add_node("enter_filter", enter_filter)
workflow.add_node("filter", filter_node)
workflow.add_node("enter_content_grader", enter_content_grader)
workflow.add_node("content_grader", content_grader)
workflow.add_node("enter_web_search", enter_web_search)
workflow.add_node("web_search", web_search)
workflow.add_node("web_search_tools", ToolNode([web_search_tool_func]))
workflow.add_node("enter_generate", enter_generate)
workflow.add_node("generate", generate)

workflow.add_edge(START, "doc_retrieval")

workflow.add_conditional_edges(
    "doc_retrieval",
    route_doc_retrieval,
    {
        "doc_retrieval_tools": "doc_retrieval_tools",
        "enter_filter": "enter_filter",
    }
)
workflow.add_edge("doc_retrieval_tools", "doc_retrieval")
workflow.add_edge("enter_filter", "filter")
workflow.add_edge("filter", "enter_content_grader")
workflow.add_edge("enter_content_grader", "content_grader")
workflow.add_conditional_edges(
    "content_grader",
    route_content_grader,
    {
        "enter_web_search": "enter_web_search",
        "enter_generate": "enter_generate",
    }
)

workflow.add_edge("enter_web_search", "web_search")
workflow.add_conditional_edges(
    "web_search",
    route_web_search,
    {
        "web_search_tools": "web_search_tools",
        "enter_generate": "enter_generate"
    }
)
workflow.add_edge("web_search_tools", "web_search")
workflow.add_edge("enter_generate", "generate")
workflow.add_edge("generate", END)

app = workflow.compile()

import sys
import os
from pathlib import Path
from typing import Any

import streamlit as st
import asyncio
import logging
from dotenv import load_dotenv

# Load environment variables (force override on hot reload)
load_dotenv(override=True)

from aegis import (
    Aegis,
    GroqProvider,
    OpenAIProvider,
    NVIDIAProvider,
    OllamaProvider,
    AnthropicProvider,
    GeminiProvider,
)
from demotools.tools import (
    github_read_repos, github_read_issues, github_read_prs, github_create_issue, github_search_commits,
    email_read_inbox, email_send, email_reply,
    db_query, db_insert, db_update, db_backup_table, db_restore_table,
    youtube_read_transcript
)

# Layer 4 Imports
from aegis.packages.models import MemorySource
from aegis.packages.memory.registry import MemoryRegistry
from aegis.packages.memory.adapters.langgraph_adapter import LangGraphMemoryAdapter
from aegis.packages.memory.manager import MemoryManager
from aegis.packages.memory.semantic import SemanticMemory
from aegis.packages.memory.retrieval import KnowledgeRetrieval
from aegis.packages.observability.store import AegisCloudExecutionStore
from langchain_core.tools import tool

st.set_page_config(page_title="Aegis Cloud Support", page_icon="🛡️", layout="wide")

st.title("🛡️ Aegis Cloud Customer Support")
st.markdown("A working prototype of the Aegis SDK Agentic Support System with full Multi-Layer Security & Governance.")

# --- Initialization (Cached) ---
@st.cache_resource
def init_memory():
    registry = MemoryRegistry()
    adapter = LangGraphMemoryAdapter()
    registry.register_provider("default_memory", adapter)
    
    registry.register_source(MemorySource(
        name="knowledge_base", provider_name="default_memory", namespace="semantic_docs", scope="global", semantic=True
    ))
    registry.register_source(MemorySource(
        name="secure_vault", provider_name="default_memory", namespace="vault", scope="global", metadata={"read_only": True}
    ))
    
    manager = MemoryManager(registry)
    retrieval = KnowledgeRetrieval(SemanticMemory(manager, "knowledge_base"))
    return adapter, manager, retrieval

adapter, manager, retrieval = init_memory()

# Define the query tool
@tool
async def query_knowledge(query: str) -> str:
    """Query the internal knowledge base for project information."""
    results = await retrieval.retrieve(query, top_k=1)
    if results:
        return results[0].content
    return "No results found."


def create_agent(framework: str = "Native Aegis SDK", provider_obj: Any = None):
    tools = [
        github_read_repos, github_read_issues, github_read_prs, github_create_issue, github_search_commits,
        email_read_inbox, email_send, email_reply,
        db_query, db_insert, db_update, db_backup_table, db_restore_table,
        query_knowledge, youtube_read_transcript
    ]

    if provider_obj is None:
        # Toggle whichever developer provider you want to test:
        provider_obj = GroqProvider(model_id="openai/gpt-oss-120b")
        

    agent = (
        Aegis(name="support-agent")
        .with_provider(provider_obj)
        .with_memory(adapter)
        .with_system_prompt(
            "You are an Aegis Cloud enterprise support agent.\n\n"
            "RULES:\n"
            "1. Complete multi-step tasks fully and autonomously. Do not pause for confirmation mid-chain.\n"
            "2. When sending emails, include the COMPLETE structured data from any tool results — "
            "names, emails, IDs, statuses, amounts, all fields. Never paraphrase or truncate.\n"
            "3. Do not hallucinate data. Only report what tools actually return.\n"
            "4. Use the minimum tools necessary to fulfil the request.\n"
            "5. End every response with a clear, brief summary of what was done.\n"
            "6. If your previous action was blocked with '⚠️ Action Requires Approval' and the user replies 'I approve', you MUST immediately execute the tools that you originally intended to use for their initial request."
        )
        .with_tools(tools)
        .with_policy([
            "Do not allow any prompts asking to hack or compromise secure databases.",
            "Always be polite and respectful.",
            "You are allowed to send emails to any external address if explicitly requested.",
        ])
    )

    if framework == "LangGraph Adapter":
        from langgraph.prebuilt import create_react_agent
        if hasattr(provider_obj, "get_chat_model"):
            llm = provider_obj.get_chat_model()
        else:
            from langchain_groq import ChatGroq
            llm = ChatGroq(model="llama-3.3-70b-versatile")
        langgraph_agent = create_react_agent(llm, tools=tools)  # type: ignore[arg-type]
        agent = agent.with_adapter("langgraph", langgraph_agent)

    elif framework == "CrewAI Adapter":
        from crewai import Agent, Task, Crew, Process, LLM
        from crewai.tools import tool as crewai_tool
        
        @crewai_tool("youtube_read_transcript")
        def crewai_youtube_read_transcript(video_url_or_id: str) -> str:
            """Read the transcript of a YouTube video given its URL or video_id."""
            from demotools.tools import youtube_read_transcript
            return youtube_read_transcript.invoke({"video_url_or_id": video_url_or_id})

        @crewai_tool("db_insert")
        def crewai_db_insert(table: str, data_json: str) -> str:
            """Insert data into a Supabase table. data_json must be a JSON string of a dictionary."""
            from demotools.tools import db_insert
            return db_insert.invoke({"table": table, "data_json": data_json})

        crew_tools = [crewai_youtube_read_transcript, crewai_db_insert]
            
        llm = LLM(
            model="openai/llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ.get("GROQ_API_KEY", "")
        )
        
        yt_agent = Agent(
            role='YouTube Content Summarizer',
            goal='Summarize YouTube videos and extract key insights based on transcripts',
            backstory='You are an expert at extracting key insights from video transcripts.',
            tools=crew_tools,
            llm=llm,
            verbose=True
        )
        
        task = Task(
            description='{prompt}',
            expected_output='A clear summary and response based on the prompt.',
            agent=yt_agent
        )
        
        crew = Crew(
            agents=[yt_agent],
            tasks=[task],
            process=Process.sequential
        )
        
        agent = agent.with_adapter("crewai", crew)

    return agent

# --- UI State ---
import uuid
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "framework" not in st.session_state:
    st.session_state.framework = "Native Aegis SDK"

# Layout
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Chat Interface")
    
    # Display chat messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat Input
    if prompt := st.chat_input("How can I help you today? (e.g. 'Refund my last order')"):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Processing request through Aegis Security Layers..."):
                agent = create_agent(st.session_state.framework)
                
                import concurrent.futures

                thread_id = st.session_state.thread_id
                effective_prompt = prompt
                _approval_phrases = {"i approve", "approve", "yes", "go ahead", "proceed"}
                if prompt.strip().lower() in _approval_phrases:
                    original_request = next(
                        (m["content"] for m in reversed(st.session_state.messages[:-1])
                         if m["role"] == "user" and m["content"].strip().lower() not in _approval_phrases),
                        None
                    )
                    if original_request:
                        effective_prompt = (
                            f"I approve. Please now execute the original request: {original_request}"
                        )

                def run_in_thread():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        async def _run():
                            async with agent:
                                return await agent.run(
                                    effective_prompt,
                                    execution_id=str(uuid.uuid4()),
                                    correlation_id=thread_id
                                )
                        return loop.run_until_complete(_run())
                    finally:
                        loop.close()

                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(run_in_thread)
                        result = future.result(timeout=120)  # 2 min timeout
                    if result is not None:
                        response_text = getattr(result, "output", str(result))
                        res_metadata = getattr(result, "metadata", {}) or {}
                        if isinstance(res_metadata, dict) and "layer1" in res_metadata:
                            st.session_state.last_layer1 = res_metadata["layer1"]
                        else:
                            st.session_state.last_layer1 = None
                    else:
                        response_text = "No response generated."
                        st.session_state.last_layer1 = None
                except Exception as e:
                    error_msg = str(e)
                    import re
                    if "attempted to call tool" in error_msg:
                        match = re.search(r"attempted to call tool '([^']+)'", error_msg)
                        if match:
                            error_msg = f"The AI hallucinated and attempted to use a tool that doesn't exist: `{match.group(1)}`. Please try rephrasing your request."
                    elif "Error code: 400" in error_msg and "'message':" in error_msg:
                        match = re.search(r"'message':\s*\"([^\"]+)\"", error_msg)
                        if match:
                            error_msg = f"LLM Provider Error: {match.group(1)}"
                    
                    response_text = f"🚨 **Agent Execution Blocked:** {error_msg}"
                    st.session_state.last_layer1 = None

                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
        
        st.rerun()

with col2:
    st.subheader("Framework & Engine")
    st.session_state.framework = st.radio(
        "Execution Source",
        ["Native Aegis SDK", "LangGraph Adapter", "CrewAI Adapter"],
        index=["Native Aegis SDK", "LangGraph Adapter", "CrewAI Adapter"].index(st.session_state.framework),
        help="Switching the engine changes the Layer 3 execution runtime, while keeping Aegis Layer 1 & 2 governance intact."
    )
    st.divider()

    st.subheader("Governance & Layers")
    st.markdown("Inspect Layer 1 (Request Intelligence) & Layer 2 (Admission) metadata here.")
    
    if "last_layer1" in st.session_state and st.session_state.last_layer1:
        l1 = st.session_state.last_layer1
        st.success("✅ Request Approved by Layer 2")
        st.json({
            "Intent": l1.intent,
            "Task Category": l1.task_category,
            "Capabilities Required": l1.capabilities,
            "Risk Level": l1.risk_level,
            "Allowed Tools": l1.allowed_tools,
            "Confidence": f"{int(l1.confidence_score * 100)}%"
        })
    elif "messages" in st.session_state and len(st.session_state.messages) > 0 and st.session_state.messages[-1]["role"] == "assistant" and "Blocked" in st.session_state.messages[-1]["content"]:
        st.error("❌ Request Blocked by Layer 2 or Policy")
        st.markdown("The system prevented execution due to a policy violation or risk threshold.")
    else:
        st.info("Submit a request to see Aegis layer intelligence.")

    st.divider()
    st.markdown("**Available Real-Time Tools:**")
    st.markdown("""
    **GitHub:** `github_read_repos`, `github_read_issues`, `github_read_prs`, `github_create_issue`, `github_search_commits`  
    **Email:** `email_read_inbox`, `email_send`, `email_reply`  
    **Supabase Database:** `db_query`, `db_insert`, `db_update`, `db_backup_table`, `db_restore_table`  
    **YouTube:** `youtube_read_transcript`
    """)

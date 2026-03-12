"""Streamlit chat interface for MCP Docs Server with Groq LLM integration."""

import asyncio
import json

import streamlit as st
from groq import Groq

from src.mcp_docs_server.pipeline.resolver import URLResolver
from src.mcp_docs_server.pipeline.scraper import scrape_page_sync

# ---------------------------------------------------------------------------
# Available Groq models (free-tier friendly)
# ---------------------------------------------------------------------------
GROQ_MODELS = {
    "llama-3.3-70b-versatile": "Llama 3.3 70B (best quality)",
    "llama-3.1-8b-instant": "Llama 3.1 8B (fastest)",
    "mixtral-8x7b-32768": "Mixtral 8x7B (32k context)",
    "gemma2-9b-it": "Gemma 2 9B",
}

SYSTEM_PROMPT = """\
You are a helpful documentation assistant. You help developers find and understand \
package documentation.

You have access to two tools:
1. **resolve_docs** – find official documentation URLs for a package.
2. **scrape_page** – fetch and read the content of a documentation page.

Workflow:
- When the user asks about a library/package, ALWAYS call resolve_docs first to find URLs.
- Then call scrape_page on the most relevant URL to read the actual docs.
- After getting the scraped content, summarize it clearly for the user.
- Always cite the source URL.
- If the user asks a general question not about a specific package, just answer normally.
"""

# ---------------------------------------------------------------------------
# Groq tool definitions (native function calling)
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "resolve_docs",
            "description": (
                "Resolve a package name to its top-5 official documentation URLs. "
                "Use this whenever the user asks about a library or package."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Exact package name as on npm or PyPI (e.g. 'react', 'fastapi', 'next.js')",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-5 specific technical terms from the user question (e.g. ['useEffect', 'cleanup'])",
                    },
                    "version": {
                        "type": "string",
                        "description": "Optional version string (e.g. '18', '4.0'). Omit if irrelevant.",
                    },
                },
                "required": ["package_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_page",
            "description": "Scrape a documentation page at the given URL and return its content as markdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the documentation page to scrape.",
                    },
                },
                "required": ["url"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Async helpers that call the existing pipeline code
# ---------------------------------------------------------------------------

async def _resolve_docs(package_name: str, keywords: list[str] | None = None, version: str | None = None) -> list[dict]:
    async with URLResolver() as resolver:
        results = await resolver.resolve(package_name, keywords=keywords, version=version)
    return [r.model_dump() for r in results]


def run_async(coro):
    """Run an async coroutine from sync Streamlit code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def execute_tool_call(tool_name: str, args: dict) -> str:
    """Execute a tool call and return the result as a JSON string."""
    if tool_name == "resolve_docs":
        results = run_async(_resolve_docs(
            package_name=args["package_name"],
            keywords=args.get("keywords"),
            version=args.get("version"),
        ))
        return json.dumps(results, indent=2)
    elif tool_name == "scrape_page":
        # Runs in a subprocess to avoid Playwright+Windows thread issues.
        results = scrape_page_sync(url=args["url"])
        return json.dumps(results, indent=2)
    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="MCP Docs Assistant", page_icon="📚", layout="wide")

st.title("📚 MCP Docs Assistant")
st.caption("Ask about any package's documentation — powered by Groq + MCP pipeline")

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Configuration")

    api_key = st.text_input("Groq API Key", type="password", placeholder="gsk_...")

    model = st.selectbox(
        "Model",
        options=list(GROQ_MODELS.keys()),
        format_func=lambda k: GROQ_MODELS[k],
    )

    temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.1)

    st.divider()
    st.markdown("**Example prompts:**")
    st.markdown("- How do I use `useEffect` in React?")
    st.markdown("- Show me FastAPI dependency injection docs")
    st.markdown("- What's new in Next.js 14?")
    st.markdown("- How does Pydantic model validation work?")

    st.divider()
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    if msg["role"] == "tool":
        continue  # tool results are shown inline during generation
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask about a package or its docs..."):
    if not api_key:
        st.error("Please enter your Groq API key in the sidebar.")
        st.stop()

    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build messages for Groq (only system + user/assistant, skip tool msgs for display history)
    groq_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in st.session_state.messages:
        if msg["role"] in ("user", "assistant"):
            groq_messages.append({"role": msg["role"], "content": msg["content"]})

    client = Groq(api_key=api_key)

    with st.chat_message("assistant"):
        # First LLM call with tools
        with st.spinner("Thinking..."):
            response = client.chat.completions.create(
                model=model,
                messages=groq_messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=2048,
            )
        
        response_message = response.choices[0].message

        # Tool-call loop: keep going while the model requests tool calls (max 5 rounds)
        rounds = 0
        while response_message.tool_calls and rounds < 5:
            rounds += 1

            # Add assistant's message (with tool_calls) to conversation
            groq_messages.append(response_message)

            # Execute each tool call the model requested
            for tool_call in response_message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                with st.status(f"🔧 Calling **{fn_name}**...", expanded=True) as status:
                    st.json(fn_args)
                    try:
                        tool_result = execute_tool_call(fn_name, fn_args)
                        # Show a preview of the result
                        preview = tool_result[:3000] + ("..." if len(tool_result) > 3000 else "")
                        st.code(preview, language="json")
                        status.update(label=f"✅ **{fn_name}** complete", state="complete")
                    except Exception as e:
                        tool_result = json.dumps({"error": str(e)})
                        status.update(label=f"❌ **{fn_name}** failed", state="error")
                        st.error(str(e))

                # Feed the tool result back to the model
                groq_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

            # Call the model again with tool results
            with st.spinner("Processing results..."):
                response = client.chat.completions.create(
                    model=model,
                    messages=groq_messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=temperature,
                    max_tokens=4096,
                )
            response_message = response.choices[0].message

        # Display the final text answer
        final_text = response_message.content or ""
        st.markdown(final_text)
        st.session_state.messages.append({"role": "assistant", "content": final_text})

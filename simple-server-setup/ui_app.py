# ui_app.py
import asyncio
import nest_asyncio
import streamlit as st

from client_sse import MCPOpenAIClient, SSE_URL  # <- your SSE client + endpoint

# Allow re-entrant loop usage (Streamlit reruns the script)
nest_asyncio.apply()

st.set_page_config(page_title="MCP + OpenAI Chat", page_icon="🤖")

# Single event loop for the whole Streamlit session
@st.cache_resource(show_spinner=False)
def get_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    return loop

# Single shared MCP+OpenAI client
@st.cache_resource(show_spinner=False)
def get_client() -> MCPOpenAIClient:
    return MCPOpenAIClient(model="gpt-4o")

def ensure_connected(loop: asyncio.AbstractEventLoop, client: MCPOpenAIClient):
    if client.session is None:
        loop.run_until_complete(client.connect_to_server(SSE_URL))

loop = get_loop()
client = get_client()

st.title("🤖 MCP + OpenAI Chat (SSE)")
st.caption("The LLM calls your MCP tools over SSE and can chain them until the task is done.")

# Init history
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "Hi! How can I help?"}]

# Replay history
for m in st.session_state["messages"]:
    st.chat_message("assistant" if m["role"] == "assistant" else "user").write(m["content"])

# User input
user = st.chat_input("Type here…")
if user:
    st.session_state["messages"].append({"role": "user", "content": user})
    st.chat_message("user").write(user)

    # live log area for steps
    steps_box = st.container()

    def on_step(event: dict):
        etype = event.get("type")
        if etype == "plan":
            steps_box.info(f"🧠 Model plan/thoughts: {event.get('message','').strip()}")
        elif etype == "tool_call":
            steps_box.write(
                f"🔧 **Calling tool** `{event.get('name')}` with args: `{event.get('args')}`"
            )
        elif etype == "tool_result":
            # keep it concise; you can pretty-print JSON if needed
            steps_box.success(f"✅ **Result from `{event.get('name')}`**:\n\n{event.get('result')}")
        elif etype == "final":
            steps_box.write("🏁 **Finalizing answer...**")

    with st.spinner("Thinking…"):
        try:
            # connect once
            ensure_connected(loop, client)
            # process on the SAME loop, with live step callback
            reply = loop.run_until_complete(client.process_query(user, on_step=on_step))
        except Exception as e:
            reply = f"Error: {e}"

    st.session_state["messages"].append({"role": "assistant", "content": reply})
    st.chat_message("assistant").write(reply)
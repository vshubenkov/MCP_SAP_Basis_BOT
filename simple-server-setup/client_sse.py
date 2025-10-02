# client_sse.py
import asyncio
import json
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.sse import sse_client
from openai import AsyncOpenAI

from pathlib import Path
import os

# ---------- load .env explicitly ----------
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"   # adjust if your .env lives elsewhere
load_dotenv(ENV_PATH, override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError(f"OPENAI_API_KEY not found. Expected in: {ENV_PATH}")

SSE_URL = os.getenv("MCP_SSE_URL", "http://localhost:8050/sse")


class MCPOpenAIClient:
    """Client for interacting with OpenAI models using MCP tools over SSE."""

    def __init__(self, model: str = "gpt-4o"):
        """Initialize the OpenAI MCP client.

        Args:
            model: The OpenAI model to use.
        """
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.openai_client = AsyncOpenAI()  # reads OPENAI_API_KEY from env
        self.model = model
        self._tools_cache: Optional[list[dict]] = None
        self._tool_result_cache: dict[tuple, str] = {}
        self.sessions: dict[str, dict] = {} 
        # SSE streams
        self._read = None
        self._write = None

    async def connect_to_server(self, sse_url: str = SSE_URL):
        """Connect to an MCP server via SSE.

        Args:
            sse_url: The server SSE endpoint, e.g. "http://localhost:8050/sse".
        """
        # Open SSE transport
        read_stream, write_stream = await self.exit_stack.enter_async_context(
            sse_client(sse_url)
        )
        self._read, self._write = read_stream, write_stream

        # Bind MCP session
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self._read, self._write)
        )

        # Initialize the connection
        await self.session.initialize()

        # List available tools
        tools_result = await self.session.list_tools()
        print("\nConnected to server with tools:")
        for tool in tools_result.tools:
            print(f"  - {tool.name}: {tool.description}")

        self._tools_cache = await self.get_mcp_tools()

    async def get_mcp_tools(self) -> list[dict]:
        if self._tools_cache is not None:
            return self._tools_cache
        tools_result = await self.session.list_tools()
        self._tools_cache = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema,
                },
            }
            for t in tools_result.tools
        ]
        return self._tools_cache
    
    def _get_session_state(self, session_id: str) -> dict:
        if session_id not in self.sessions:
            self.sessions[session_id] = {"history": [], "summary": ""}
        return self.sessions[session_id]

    async def _summarize_if_needed(
        self,
        session_state: dict,
        max_chars: int = 8000,          # rough threshold before we summarize
        target_chars: int = 1500        # target size of the summary
        ):
        # If the serialized history is too big, summarize it into session_state["summary"]
        serialized = json.dumps(session_state["history"], ensure_ascii=False)
        if len(serialized) < max_chars:
            return

        prompt = (
            "Summarize the following chat history into a concise brief that preserves:\n"
            "- user goals & constraints\n"
            "- important facts (names, ids, emails)\n"
            "- decisions taken and current state\n\n"
            "Keep it under about 1500 characters.\n\n"
            f"History JSON:\n{serialized}"
        )

        resp = await self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that writes concise summaries."},
                {"role": "user", "content": prompt},
            ],
        )
        summary = resp.choices[0].message.content or ""
        session_state["summary"] = summary
        # Trim raw history aggressively after summarizing
        session_state["history"] = session_state["history"][-6:]  # keep a small tail
    
    def _assistant_to_dict(self, msg) -> dict:
        """
        Convert OpenAI SDK ChatCompletionMessage to a plain dict suitable for the next request.
        """
        tool_calls = []
        for tc in (msg.tool_calls or []):
            # tc.function.arguments is already a JSON string per OpenAI API
            tool_calls.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            })
        return {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": tool_calls if tool_calls else None,
        }
    
    
    async def process_query(
        self,
        query: str,
        *,
        session_id: str = "default",
        max_rounds: int = 6,
        on_step: Optional[callable] = None,
        ) -> str:
        """
        Process a query using OpenAI and available MCP tools.

        Args:
            query: The user query.
            max_rounds: safety cap for tool-chaining.
            on_step: optional callback(dict) to report progress events:
                     {"type":"plan"|"tool_call"|"tool_result"|"final", ...}
        """
        if not self.session:
            raise RuntimeError("MCP session is not initialized. Call connect_to_server() first.")
        
        session_state = self._get_session_state(session_id)
        tools = await self.get_mcp_tools()

        system_msg = {
            "role": "system",
            "content": (
                "You can use MCP tools. Keep calling tools until the user request is fully completed. "
                "Only send a final assistant message when all required tools have been called and "
                "their results are incorporated. If essential info is missing, ask the user."
            )
        }
        
        messages: list[dict] = [system_msg]
        if session_state["summary"]:
            messages.append({"role": "system", "content": f"Conversation summary:\n{session_state['summary']}"})
        # include recent history
        messages += session_state["history"][-10:]   # rolling window
        # latest user turn
        user_msg = {"role": "user", "content": query}
        messages.append(user_msg)

        for round_idx in range(max_rounds):
            resp = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            assistant_message = resp.choices[0].message
            assistant_dict = self._assistant_to_dict(assistant_message)
            messages.append(assistant_dict)

            # (Optional) surface high-level plan/assistant thoughts if you want
            if on_step and assistant_message.content:
                on_step({"type": "plan", "round": round_idx + 1, "message": assistant_message.content})

            tool_calls = assistant_message.tool_calls or []
            if not tool_calls:
                # Final answer — persist to session history
                final_text = assistant_message.content or ""
                # ✅ append the plain dict, not the SDK object
                session_state["history"].extend([user_msg, assistant_dict])
                # maybe summarize now that we added messages
                await self._summarize_if_needed(session_state)
                if on_step:
                    on_step({"type": "final", "content": final_text})
                return final_text

            # Execute all requested tools concurrently
            async def run_one(tc):
                name = tc.function.name
                args_json = tc.function.arguments or "{}"
                try:
                    args = json.loads(args_json)
                except Exception:
                    args = {}

                if on_step:
                    on_step({"type": "tool_call", "name": name, "args": args})

                # Simple deterministic cache
                cache_key = (name, tuple(sorted(args.items())))
                if cache_key in self._tool_result_cache:
                    tool_text = self._tool_result_cache[cache_key]
                else:
                    result = await self.session.call_tool(name, arguments=args)
                    parts = []
                    for item in result.content:
                        t = getattr(item, "text", None)
                        if t:
                            parts.append(t)
                    tool_text = "\n".join(parts) or str(result)
                    self._tool_result_cache[cache_key] = tool_text

                if on_step:
                    on_step({"type": "tool_result", "name": name, "result": tool_text})

                # Return the tool message to add
                return {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_text,
                }

            tool_messages = await asyncio.gather(*[run_one(tc) for tc in tool_calls])
            messages.extend(tool_messages)

        # Fallback if too many rounds
        fallback = "Sorry, I couldn't complete this in time. Please try again."
        session_state["history"].extend([user_msg, {"role": "assistant", "content": fallback}])
        await self._summarize_if_needed(session_state)
        if on_step:
            on_step({"type": "final", "content": fallback})
        return fallback
    
    async def cleanup(self):
        """
        Cleanly close SSE + session. Safe to call multiple times.
        """
        try:
            await self.exit_stack.aclose()
        finally:
            self.session = None
            self._read = None
            self._write = None

# --- quick debug runner -------------------------------------------------------
def _print_step(event: dict):
    etype = event.get("type")
    if etype == "plan":
        print(f"\n[PLAN] {event.get('message', '').strip()}")
    elif etype == "tool_call":
        print(f"[TOOL→] {event.get('name')} args={event.get('args')}")
    elif etype == "tool_result":
        # keep concise; print first line only
        res = (event.get("result") or "").splitlines()[:1]
        print(f"[TOOL✓] {event.get('name')} result={res[0] if res else ''}")
    elif etype == "final":
        print("[FINAL] assembling answer...")

async def _debug_run():
    """
    Minimal debug harness:
    - connects once to the SSE MCP server
    - runs a few prompts in sequence
    - prints live steps (plan, tool calls, tool results, final)
    """
    client = MCPOpenAIClient(model="gpt-4o")
    # If you want to change URL quickly during debug:
    sse_url = os.getenv("MCP_SSE_URL", "http://localhost:8050/sse")

    # 1) connect once
    await client.connect_to_server(sse_url)

    # 2) define your test prompts here
    prompts = [
        "Please get my SAP username for viacheslav.shubenkov@zumtobelgroup.com and reset the password.",
        "ok, Z12",
        "Nice job"
    ]

    # 3) run them one-by-one with live step logging
    for i, q in enumerate(prompts, start=1):
        print("\n" + "="*70)
        print(f"[TEST {i}] {q}")
        print("="*70)
        try:
            answer = await client.process_query(q, session_id="debug", on_step=_print_step)
            print("\n[ANSWER]", answer, "\n")
        except Exception as e:
            print(f"[ERROR] {e}")

    # 4) optional: close nicely (useful when stepping in debugger)
    await client.cleanup()

# if __name__ == "__main__":
#     asyncio.run(_debug_run())

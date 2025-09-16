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

    async def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Get available tools from the MCP server in OpenAI format."""
        if not self.session:
            raise RuntimeError("MCP session is not initialized. Call connect_to_server() first.")

        tools_result = await self.session.list_tools()
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in tools_result.tools
        ]

    async def process_query(self, query: str, *, max_rounds: int = 6, on_step=None) -> str:
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
        
        tools = await self.get_mcp_tools()

        system_msg = {
            "role": "system",
            "content": (
                "You can use MCP tools. Keep calling tools until the user request is fully completed. "
                "Only send a final assistant message when all required tools have been called and "
                "their results are incorporated. If essential info is missing, ask the user."
            )
        }
        
        messages: list[dict] = [system_msg, {"role": "user", "content": query}]
        
        for round_idx in range(max_rounds):
            # Ask the model what to do next
            resp = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            assistant_message = resp.choices[0].message
            messages.append(assistant_message)

            # (Optional) surface high-level plan/assistant thoughts if you want
            if on_step and assistant_message.content:
                on_step({"type": "plan", "round": round_idx + 1, "message": assistant_message.content})

            tool_calls = assistant_message.tool_calls or []
            if not tool_calls:
                # Final answer
                final_text = assistant_message.content or ""
                if on_step:
                    on_step({"type": "final", "content": final_text})
                return final_text

            # Execute all requested tools in this turn
            for tc in tool_calls:
                name = tc.function.name
                args_json = tc.function.arguments or "{}"
                try:
                    args = json.loads(args_json)
                except Exception:
                    args = {}

                if on_step:
                    on_step({"type": "tool_call", "name": name, "args": args})

                # Call MCP tool
                result = await self.session.call_tool(name, arguments=args)

                # Convert MCP content -> text
                tool_text_parts = []
                for item in result.content:
                    t = getattr(item, "text", None)
                    if t:
                        tool_text_parts.append(t)
                tool_text = "\n".join(tool_text_parts) or str(result)

                if on_step:
                    on_step({"type": "tool_result", "name": name, "result": tool_text})

                # Feed tool result back to the model
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_text,
                })

        # Safety fallback if model keeps requesting tools
        fallback = "Sorry, I couldn't complete this in time. Please try again."
        if on_step:
            on_step({"type": "final", "content": fallback})
        return fallback
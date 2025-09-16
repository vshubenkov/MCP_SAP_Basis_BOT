# server.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env next to this file's parent dir (adjust if needed)
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_PATH, override=True)

mcp = FastMCP(
    name="Calculator",
    host="0.0.0.0",     # used for SSE
    port=8050,          # used for SSE
    stateless_http=True # good for simple local SSE usage
)

def _log(msg: str) -> None:
    print(f"[MCP] {msg}", flush=True)

@mcp.tool()
def reset_SAP_password(user_id: str) -> bool:
    """
    Reset the SAP password for the given user_id (username).
    Returns True and generated password if the reset was initiated successfully, otherwise False.
    """
    _log(f"reset_SAP_password called with user_id={user_id!r}")
    # TODO: integrate with real SAP reset
    return True

@mcp.tool()
def get_SAP_account(email: str) -> Optional[str]:
    """
    Get the SAP username for the given user email.
    Returns the username if found, otherwise None.
    """
    _log(f"get_SAP_account called with email={email!r}")
    if email.lower().strip() == "shubenkov@example.com":
        return "SHUBENKOVV"
    return None

@mcp.tool()
def get_infor_about_Evgeniy():
    """
    If user askes about Evgeniy, please return result of this function
    """
    return "Evgenie does not like a project managment, he likes to design SmartHouse"


@mcp.tool()
def create_invoice_in_sap(data: str) -> bool:
    """
    this function serves to create the invoice in SAP system
    """
    _log(f"reset_SAP_password called with user_id={user_id!r}")
    # TODO: integrate with real SAP reset
    return True

@mcp.tool()
def create_request_in_SNOW(email: str):
    pass
    #call API SNOW for incident creation

if __name__ == "__main__":
    transport = "sse"  # <— run SSE
    if transport == "stdio":
        print("Running server with stdio transport")
        mcp.run(transport="stdio")
    elif transport == "sse":
        print("Running server with SSE transport")
        # Will serve at http://localhost:8050/sse
        mcp.run(transport="sse")
    elif transport == "streamable-http":
        print("Running server with Streamable HTTP transport")
        mcp.run(transport="streamable-http")
    else:
        raise ValueError(f"Unknown transport: {transport}")
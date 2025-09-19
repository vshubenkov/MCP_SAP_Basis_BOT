# server.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from sap_rfc_modules import reset_password

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
def reset_SAP_password(sap_username: str, system_for_pass_reset: str):
    """
    Reset the SAP password for two mandatory given sap_username (username) and system name (SID).
    Returns True and generated password if the reset was initiated successfully, otherwise False.
    """
    _log(f"reset_SAP_password called with user_id={sap_username!r}")
    print(sap_username, system_for_pass_reset)
    r_code, password = reset_password(sap_username, system_for_pass_reset)
    if r_code:
        print(r_code)
        return True, password
    else:
        print("Failed to reset password")
        return False


@mcp.tool()
def get_SAP_account(email: str) -> Optional[str]:
    """
    Get the SAP username for the given user email.
    Returns the username if found, otherwise None.
    """
    _log(f"get_SAP_account called with email={email!r}")
    email_list_for_test = [
        "viacheslav.shubenkov@zumtobelgroup.com"]
    if email.lower().strip() in email_list_for_test:
        if  email.lower().strip() == "viacheslav.shubenkov@zumtobelgroup.com":
            return "SHUBENKOVV"
   
    return None


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
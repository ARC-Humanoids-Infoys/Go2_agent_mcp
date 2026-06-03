from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
import sys
import time
import os
from pathlib import Path

mcp_session    = None
mcp_stream_ctx = None
mcp_connected  = False
tools_cache    = []
call_history   = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_session, mcp_stream_ctx, mcp_connected, tools_cache

    try:
        # Create server params with CURRENT environment (including any env vars set via web UI)
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).parent.parent / "server.py")],
            env=dict(os.environ)  # Pass current environment to subprocess
        )
        
        print(f"Starting MCP server with ROBOT_IP={os.environ.get('ROBOT_IP', 'NOT SET')}")
        mcp_stream_ctx = stdio_client(server_params)
        read, write    = await mcp_stream_ctx.__aenter__()
        mcp_session    = ClientSession(read, write)
        await mcp_session.__aenter__()
        await mcp_session.initialize()
        mcp_connected  = True

        resp = await mcp_session.list_tools()
        tools_cache = []
        for t in resp.tools:
            schema = {}
            if hasattr(t, "inputSchema") and t.inputSchema:
                schema = t.inputSchema if isinstance(t.inputSchema, dict) else t.inputSchema.model_dump()
            tools_cache.append({
                "name":        t.name,
                "description": t.description or "",
                "inputSchema": schema,
            })
        print(f"MCP connected — {len(tools_cache)} tools loaded")

    except Exception as e:
        mcp_connected = False
        print(f"MCP startup error: {e}")

    yield

    if mcp_session:    await mcp_session.__aexit__(None, None, None)
    if mcp_stream_ctx: await mcp_stream_ctx.__aexit__(None, None, None)
    mcp_connected = False


app = FastAPI(lifespan=lifespan)
client_dir = Path(__file__).parent
templates = Jinja2Templates(directory=str(client_dir / "templates"))
app.mount("/static", StaticFiles(directory=str(client_dir / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/status")
async def status():
    return JSONResponse({
        "server":     "running",
        "mcp":        "connected" if mcp_connected else "disconnected",
        "tool_count": len(tools_cache),
    })


@app.get("/tools")
async def list_tools():
    return JSONResponse({"tools": tools_cache})


@app.get("/env")
async def get_env():
    """Get all environment variables."""
    return JSONResponse({"env": dict(os.environ)})


@app.post("/env")
async def set_env(request: Request):
    """Set or delete an environment variable."""
    body = await request.json()
    key = body.get("key", "")
    value = body.get("value")
    
    if not key:
        return JSONResponse({"error": "Missing key"}, status_code=400)
    
    if value == "":
        # Delete the variable if value is empty string
        if key in os.environ:
            del os.environ[key]
        return JSONResponse({"ok": True, "key": key, "deleted": True})
    else:
        # Set the variable
        os.environ[key] = str(value)
        return JSONResponse({"ok": True, "key": key, "value": str(value)})


@app.get("/env/{key}")
async def get_env_var(key: str):
    """Get a specific environment variable."""
    value = os.environ.get(key)
    if value is None:
        return JSONResponse({"error": f"Env var '{key}' not found"}, status_code=404)
    return JSONResponse({"key": key, "value": value})


@app.post("/call")
async def call_tool(request: Request):
    global call_history

    if not mcp_connected or not mcp_session:
        return JSONResponse({"error": "MCP not connected"}, status_code=503)

    body      = await request.json()
    tool_name = body.get("tool", "")
    arguments = body.get("arguments", {})

    if not tool_name:
        return JSONResponse({"error": "Missing field: tool"}, status_code=400)

    t0 = time.time()
    try:
        resp    = await mcp_session.call_tool(tool_name, arguments)
        content = getattr(resp, "content", [])
        texts   = [c.text for c in content if hasattr(c, "text")]
        result  = "\n".join(texts) if texts else str(resp)
        is_err  = bool(getattr(resp, "isError", False))
        ms      = round((time.time() - t0) * 1000)

        call_history.insert(0, {
            "id": int(t0 * 1000), "tool": tool_name,
            "arguments": arguments, "result": result,
            "error": None, "duration_ms": ms,
            "ts": time.strftime("%H:%M:%S"), "is_error": is_err,
        })
        call_history = call_history[:100]

        return JSONResponse({"result": result, "duration_ms": ms, "isError": is_err})

    except Exception as e:
        ms = round((time.time() - t0) * 1000)
        call_history.insert(0, {
            "id": int(t0 * 1000), "tool": tool_name,
            "arguments": arguments, "result": None,
            "error": str(e), "duration_ms": ms,
            "ts": time.strftime("%H:%M:%S"), "is_error": True,
        })
        call_history = call_history[:100]
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/history")
async def get_history():
    return JSONResponse({"history": call_history})


@app.delete("/history")
async def clear_history():
    global call_history
    call_history = []
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
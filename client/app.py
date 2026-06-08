from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from pathlib import Path
import os
import time
import asyncio

BASE_DIR = Path(__file__).parent
MCP_SERVER_SCRIPT = str(Path(__file__).parent.parent / "server.py")

mcp_session    = None
mcp_stream_ctx = None
mcp_connected  = False
tools_cache    = []
call_history   = []
mcp_lock       = asyncio.Lock()


def _build_server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command="python3",
        args=[MCP_SERVER_SCRIPT],
        env=os.environ.copy(),
    )


async def _stop_mcp_session() -> None:
    global mcp_session, mcp_stream_ctx, mcp_connected, tools_cache

    if mcp_session:
        await mcp_session.__aexit__(None, None, None)
    if mcp_stream_ctx:
        await mcp_stream_ctx.__aexit__(None, None, None)

    mcp_session = None
    mcp_stream_ctx = None
    mcp_connected = False
    tools_cache = []


async def _start_mcp_session() -> None:
    global mcp_session, mcp_stream_ctx, mcp_connected, tools_cache

    mcp_stream_ctx = stdio_client(_build_server_params())
    read, write = await mcp_stream_ctx.__aenter__()
    mcp_session = ClientSession(read, write)
    await mcp_session.__aenter__()
    await mcp_session.initialize()
    mcp_connected = True

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


async def _restart_mcp_session() -> None:
    async with mcp_lock:
        try:
            await _stop_mcp_session()
        except Exception:
            pass
        await _start_mcp_session()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _restart_mcp_session()
        print(f"MCP connected — {len(tools_cache)} tools loaded")

    except Exception as e:
        mcp_connected = False
        print(f"MCP startup error: {e}")

    yield

    try:
        async with mcp_lock:
            await _stop_mcp_session()
    except Exception:
        pass


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


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


# ── Agent chat endpoint ──────────────────────────────────────────────────────
import sys, json as _json
from pathlib import Path as _Path

_AGENT_DIR = _Path(__file__).parent.parent / "agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

try:
    from agent import Agent as _Agent
    from fastapi.responses import StreamingResponse
    import threading as _threading
    import traceback as _traceback

    _agent_instance: "_Agent | None" = None
    _agent_init_error: str | None = None
    _agent_lock = _threading.Lock()

    def _get_agent() -> "_Agent":
        global _agent_instance, _agent_init_error
        with _agent_lock:
            if _agent_instance is None:
                try:
                    robot_ip = os.getenv("ROBOT_IP")
                    if not robot_ip:
                        raise ValueError("ROBOT_IP environment variable not set")
                    print(f"[Agent] Initializing with ROBOT_IP={robot_ip}")
                    _agent_instance = _Agent(robot_ip=robot_ip)
                    print("[Agent] Initialized successfully")
                except Exception as e:
                    _agent_init_error = str(e)
                    print(f"[Agent] Initialization failed: {e}")
                    _traceback.print_exc()
                    raise
            return _agent_instance

    @app.post("/chat")
    async def chat(request: Request):
        body = await request.json()
        message = body.get("message", "").strip()
        if not message:
            return JSONResponse({"error": "Missing field: message"}, status_code=400)

        import asyncio
        loop = asyncio.get_event_loop()

        def _run_agent():
            agent = _get_agent()
            return agent.ask_with_tools(message)

        try:
            result = await loop.run_in_executor(None, _run_agent)
            return JSONResponse({
                "content": result.get("content", ""),
                "type": result.get("type", ""),
                "tool_calls": [
                    {"name": tc.get("name"), "args": tc.get("args", {})}
                    for tc in result.get("tool_calls", [])
                ],
                "tool_results": result.get("tool_results", []),
                "steps_used": result.get("steps_used", 0),
                "step_trace": result.get("step_trace", []),
            })
        except Exception as e:
            error_msg = str(e)
            print(f"[Chat] Error: {error_msg}")
            _traceback.print_exc()
            return JSONResponse({"error": error_msg}, status_code=500)

except Exception as e:
    print(f"Warning: Agent chat not available: {e}")
    _traceback.print_exc()


@app.get("/env")
async def get_env():
    safe_keys = ["ROBOT_IP", "ANTHROPIC_API_KEY", "OLLAMA_HOST", "MODEL"]
    env_data = {k: os.environ.get(k, "") for k in safe_keys if os.environ.get(k)}
    return JSONResponse({"env": env_data})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)


@app.post("/env")
async def set_env(request: Request):
    body = await request.json()
    key = body.get("key", "").strip()
    value = body.get("value", "").strip()
    if not key:
        return JSONResponse({"error": "Missing key"}, status_code=400)
    if value:
        os.environ[key] = value
    elif key in os.environ:
        del os.environ[key]

    try:
        await _restart_mcp_session()
        return JSONResponse({"ok": True, "mcp_restarted": True})
    except Exception as e:
        return JSONResponse(
            {
                "ok": True,
                "mcp_restarted": False,
                "warning": f"Environment updated but MCP restart failed: {e}",
            }
        )
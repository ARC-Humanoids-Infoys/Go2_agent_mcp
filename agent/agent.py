import json
import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import create_model

from config import MODEL


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


def _json_schema_to_type(schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type", "string")

    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list[Any]
    if schema_type == "object":
        return dict[str, Any]

    return Any


def _create_args_model(
    tool_name: str,
    input_schema: dict[str, Any],
):
    if not input_schema or input_schema.get("type") != "object":
        return None

    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    fields = {}
    for field_name, field_schema in properties.items():
        field_type = _json_schema_to_type(field_schema)
        default_value = ... if field_name in required else None
        fields[field_name] = (field_type, default_value)

    if not fields:
        return None

    model_name = f"{tool_name.title().replace('_', '')}Args"
    return create_model(model_name, **fields)


class MCPClient:

    def __init__(
        self,
        command: str = "python3",
        server_script: Path | None = None,
        robot_ip: str | None = None,
    ):
        if server_script is None:
            server_script = ROOT_DIR / "server.py"

        env = os.environ.copy()
        if robot_ip is None:
            robot_ip = os.getenv("ROBOT_IP")
        if robot_ip:
            env["ROBOT_IP"] = robot_ip

        self.server_params = StdioServerParameters(
            command=command,
            args=[str(server_script)],
            env=env,
        )
        self.stream_ctx = None
        self.session = None
        self.tools_meta: list[dict[str, Any]] = []
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    async def _connect_async(self):
        self.stream_ctx = stdio_client(self.server_params)
        read, write = await self.stream_ctx.__aenter__()

        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()

        resp = await self.session.list_tools()
        self.tools_meta = []
        for t in resp.tools:
            schema = {}
            if hasattr(t, "inputSchema") and t.inputSchema:
                schema = (
                    t.inputSchema
                    if isinstance(t.inputSchema, dict)
                    else t.inputSchema.model_dump()
                )

            self.tools_meta.append(
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": schema,
                }
            )

        return self.tools_meta

    def connect(self):
        return self._run(self._connect_async())

    async def _call_tool_async(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> Any:
        if self.session is None:
            raise RuntimeError("MCP session not connected")

        response = await self.session.call_tool(
            tool_name,
            args or {},
        )

        content = getattr(response, "content", [])
        texts = [c.text for c in content if hasattr(c, "text")]

        if texts:
            if len(texts) == 1:
                text = texts[0]
                try:
                    return json.loads(text)
                except Exception:
                    return text
            return "\n".join(texts)

        return str(response)

    def call_tool(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> Any:
        return self._run(
            self._call_tool_async(tool_name, args)
        )

    async def _close_async(self):
        if self.session is not None:
            try:
                await self.session.__aexit__(None, None, None)
            except Exception:
                pass
            self.session = None

        if self.stream_ctx is not None:
            try:
                await self.stream_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self.stream_ctx = None

    def close(self):
        try:
            self._run(self._close_async())
        except Exception:
            pass
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2)


class Agent:

    def __init__(self, robot_ip: str | None = None):

        self.llm = init_chat_model(
            MODEL
        )

        self.mcp_client = MCPClient(robot_ip=robot_ip)
        discovered_tools = self.mcp_client.connect()

        print("Discovered MCP tools:")
        for t in discovered_tools:
            print(f"- {t['name']}")

        self.tools = {}
        generated_tools = []
        for tool_meta in discovered_tools:
            tool_name = tool_meta["name"]
            tool_description = tool_meta.get("description", "")
            input_schema = tool_meta.get("inputSchema", {})

            def _build_wrapper(name: str):
                def _wrapper(**kwargs):
                    return self.mcp_client.call_tool(
                        name,
                        kwargs,
                    )

                return _wrapper

            wrapper = _build_wrapper(tool_name)
            args_model = _create_args_model(
                tool_name=tool_name,
                input_schema=input_schema,
            )

            langchain_tool = StructuredTool.from_function(
                func=wrapper,
                name=tool_name,
                description=tool_description or f"MCP tool: {tool_name}",
                args_schema=args_model,
                infer_schema=args_model is None,
            )

            self.tools[tool_name] = langchain_tool
            generated_tools.append(langchain_tool)

        self.llm_with_tools = self.llm.bind_tools(
            generated_tools
        )

    def _is_connect_success(self, output: Any) -> bool:
        return isinstance(output, str) and output == "Connected to Go2"

    def _is_connect_retryable_failure(self, output: Any) -> bool:
        if not isinstance(output, str):
            return False

        retryable_tokens = [
            "Connection timeout",
            "Connect failed",
            "Failed to receive SDP",
            "RemoteDisconnected",
        ]

        return any(token in output for token in retryable_tokens)

    def _is_transient_data_unavailable(self, output: Any) -> bool:
        return (
            isinstance(output, str)
            and output.startswith("No ")
            and output.endswith(" data received yet")
        )

    def _invoke_tool_with_retries(
        self,
        name: str,
        args: dict[str, Any],
        tool_obj,
        max_retries: int = 2,
    ) -> Any:
        last_output = None

        for attempt in range(max_retries + 1):

            try:
                last_output = tool_obj.invoke(args)
            except Exception as e:
                last_output = f"Tool execution failed for {name}: {e}"

            if name == "connect":
                if self._is_connect_success(last_output):
                    return last_output

                if self._is_connect_retryable_failure(last_output) and attempt < max_retries:
                    time.sleep(1.0)
                    continue

                return last_output

            if self._is_transient_data_unavailable(last_output) and attempt < max_retries:
                time.sleep(0.5)
                continue

            if (
                last_output == "Not connected"
                and name != "connect"
                and "connect" in self.tools
                and attempt < max_retries
            ):
                connect_tool = self.tools["connect"]
                _ = self._invoke_tool_with_retries(
                    name="connect",
                    args={},
                    tool_obj=connect_tool,
                    max_retries=1,
                )
                time.sleep(0.5)
                continue

            return last_output

        return last_output

    def ask(
        self,
        prompt: str,
    ) -> str:

        response = self.llm.invoke(
            prompt
        )

        return response.content

    def ask_with_tools(
        self,
        prompt: str,
    ) -> dict:

        return self.ask_with_agent_loop(
            prompt=prompt,
            max_steps=6,
        )

    def ask_with_agent_loop(
        self,
        prompt: str,
        max_steps: int = 6,
    ) -> dict:

        messages = [
            HumanMessage(content=prompt)
        ]

        all_tool_calls = []
        all_tool_results = []
        step_trace = []

        for step in range(1, max_steps + 1):

            response = self.llm_with_tools.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                response_type = (
                    "normal_text_response"
                    if not all_tool_calls
                    else "tool_call_response"
                )

                return {
                    "type": response_type,
                    "content": response.content,
                    "tool_calls": all_tool_calls,
                    "tool_results": all_tool_results,
                    "steps_used": step,
                    "step_trace": step_trace,
                }

            round_calls = []
            round_results = []

            for tool_call in response.tool_calls:

                name = tool_call.get("name")
                args = tool_call.get("args", {})
                tool_obj = self.tools.get(name)

                if tool_obj is None:
                    tool_output = f"Unknown tool: {name}"
                else:
                    tool_output = self._invoke_tool_with_retries(
                        name=name,
                        args=args,
                        tool_obj=tool_obj,
                        max_retries=2,
                    )

                tool_result = {
                    "name": name,
                    "args": args,
                    "result": tool_output,
                }

                round_calls.append(tool_call)
                round_results.append(tool_result)
                all_tool_calls.append(tool_call)
                all_tool_results.append(tool_result)

                messages.append(
                    ToolMessage(
                        content=json.dumps(
                            tool_output,
                            ensure_ascii=False,
                            default=str,
                        ),
                        tool_call_id=tool_call.get("id", f"step-{step}-{name}"),
                    )
                )

            step_trace.append(
                {
                    "step": step,
                    "tool_calls": round_calls,
                    "tool_results": round_results,
                }
            )

        return {
            "type": "max_steps_reached",
            "content": f"Agent stopped after reaching max_steps={max_steps} without a final answer.",
            "tool_calls": all_tool_calls,
            "tool_results": all_tool_results,
            "steps_used": max_steps,
            "step_trace": step_trace,
        }

    def close(self):
        self.mcp_client.close()

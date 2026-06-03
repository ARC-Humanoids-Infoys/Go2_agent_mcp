from agent import Agent
import os

robot_ip = os.getenv("ROBOT_IP")

agent = Agent(robot_ip=robot_ip)

try:
    # connect_result = agent.mcp_client.call_tool("connect", {})
    # print("Connect result:")
    # print(connect_result)

    result = agent.ask_with_tools(
        "Turn 90 degrees and then tell me the new orientation."
    )

    print("Response type:")
    print(result["type"])

    print("\nTool calls:")
    print(result["tool_calls"])

    print("\nTool results:")
    print(result["tool_results"])

    print("\nFinal answer:")
    print(result["content"])

    if result["tool_calls"]:
        print("\nResult: tool_call generated")
    else:
        print("\nResult: normal text response")
finally:
    agent.close()

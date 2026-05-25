from mcp.server.fastmcp import FastMCP
from controllers.go2_controller import Go2Controller


mcp = FastMCP("go2_agent")

controller = Go2Controller()


@mcp.tool()
def connect():

    result = controller.connect()

    return result


@mcp.tool()
def move(
    x: float = 0,
    y: float = 0,
    yaw: float = 0,
    duration: float = 0
):

    result = controller.move(
        x=x,
        y=y,
        yaw=yaw,
        duration=duration
    )

    return (
        "Movement command sent"
        if result
        else
        "Movement failed"
    )


@mcp.tool()
def stop():

    controller.stop()

    return "Stopped"


@mcp.tool()
def disconnect():

    controller.disconnect()

    return "Disconnected"


if __name__ == "__main__":
    mcp.run(
        transport="stdio"
    )
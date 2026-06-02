from mcp.server.fastmcp import FastMCP
from controllers.go2_controller import Go2Controller
from controllers.navigation_manager import NavigationManager


mcp = FastMCP("go2_agent")

controller = Go2Controller()
navigation_manager = NavigationManager()


@mcp.tool()
def connect():

    result = controller.connect()

    return result

@mcp.tool()
def inspect_connection():

    if not controller.conn:
        return "Not connected"

    return str(
        dir(controller.conn)
    )

@mcp.tool()
def inspect_datachannel():

    if not controller.conn:
        return "Not connected"

    return str(
        dir(controller.conn.datachannel)
    )


@mcp.tool()
def inspect_rtc_inner_req():

    if not controller.conn:
        return "Not connected"

    return str(
        dir(
            controller.conn.datachannel.rtc_inner_req
        )
    )

@mcp.tool()
def inspect_pub_sub():

    if not controller.conn:
        return "Not connected"

    return str(
        dir(
            controller.conn.datachannel.pub_sub
        )
    )
@mcp.tool()
def test_low_state():
    return controller.test_low_state()


@mcp.tool()
def test_odom():
    """Subscribe to ROBOTODOM and return the raw message for inspection."""
    return controller.test_odom()


@mcp.tool()
def get_position():
    """Get robot position from ROBOTODOM."""
    return controller.get_position()


@mcp.tool()
def get_orientation():
    """Get robot orientation from ROBOTODOM."""
    return controller.get_orientation()


@mcp.tool()
def get_pose():
    """Get robot pose (position + orientation) from ROBOTODOM."""
    return controller.get_pose()


@mcp.tool()
def set_reference_pose():
    """Set current pose as reference for distance checks."""
    return controller.set_reference_pose()


@mcp.tool()
def distance_from_reference():
    """Measure 2D distance from previously set reference pose."""
    return controller.distance_from_reference()


@mcp.tool()
def measure_distance_traveled():
    """Alias for distance_from_reference()."""
    return controller.measure_distance_traveled()


@mcp.tool()
def move_forward_distance(
    distance_meters: float,
    speed: float = 0.4,
    timeout_s: float = 20.0,
    tolerance_m: float = 0.02,
):
    """Move forward until odometry distance target is reached."""
    return controller.move_forward_distance(
        distance_meters=distance_meters,
        speed=speed,
        timeout_s=timeout_s,
        tolerance_m=tolerance_m,
    )


@mcp.tool()
def turn_degrees(
    degrees: float,
    yaw_speed: float = 0.5,
    timeout_s: float = 20.0,
    tolerance_deg: float = 3.0,
):
    """Turn robot by relative angle using odometry feedback."""
    return controller.turn_degrees(
        degrees=degrees,
        yaw_speed=yaw_speed,
        timeout_s=timeout_s,
        tolerance_deg=tolerance_deg,
    )


@mcp.tool()
def get_imu():
    """Get roll, pitch, yaw from the robot IMU."""
    return controller.get_imu()


@mcp.tool()
def get_battery():
    """Get battery state: charge %, voltage, current, cycle count."""
    return controller.get_battery()


@mcp.tool()
def get_motor_states():
    """Get joint angles and temperatures for all 12 leg motors."""
    return controller.get_motor_states()


@mcp.tool()
def get_foot_forces():
    """Get foot contact forces for FR, FL, RR, RL feet."""
    return controller.get_foot_forces()


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
def set_goal(
    x: float,
    y: float,
):
    """Set navigation goal in MCP-friendly x/y format."""
    return navigation_manager.set_goal(x=x, y=y)


@mcp.tool()
def get_navigation_state():
    """Get current navigation state and active goal."""
    return navigation_manager.get_navigation_state()


@mcp.tool()
def is_goal_reached():
    """Check whether current goal has been reached."""
    return navigation_manager.is_goal_reached()


@mcp.tool()
def cancel_goal():
    """Cancel current goal and return to IDLE."""
    return navigation_manager.cancel_goal()

@mcp.tool()
def execute_sport_command(
    command_name: str
):

    result = controller.execute_sport_command(
        command_name=command_name
    )

    return result



@mcp.tool()
def list_sport_commands():

    return controller.list_sport_commands()


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
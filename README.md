# Go2 Agent MCP

MCP server for Unitree Go2 using WebRTC.

This project exposes robot control, telemetry, odometry, and navigation as MCP tools so any MCP client (for example MCP Inspector) can control and query the robot.

## What is implemented

- WebRTC connection to Go2 via `unitree_webrtc_connect_leshy`
- FastMCP server with STDIO transport
- Real-time velocity movement control
- Sport command discovery and execution (`SPORT_CMD` mapping)
- LOW_STATE telemetry parsing (IMU, battery, motors, foot forces)
- ROBOTODOM parsing (position, orientation, pose)
- Distance and heading utilities from odometry
- Closed-loop motion primitives:
  - Move forward by distance
  - Turn by relative angle
- Navigation manager with background control loop:
  - Set goal
  - Start/stop navigator loop
  - Goal status and goal reached checks
  - Cancel goal

---

## Architecture

```text
MCP Client (Inspector / Agent)
            ↓
       FastMCP Server
            ↓
      Go2Controller  ↔  NavigationManager
            ↓
 UnitreeWebRTCConnection (LocalSTA)
            ↓
      WebRTC DataChannel
            ↓
         Unitree Go2
```

---

## Project structure

```text
go2_agent/
├── server.py
├── requirements.txt
├── README.md
├── main.py
└── controllers/
    ├── go2_controller.py
    ├── navigation_manager.py
    └── wireless_controller_old.py
```

Notes:
- `navigation_manager.py` contains the autonomous goal-following worker loop.
- `wireless_controller_old.py` is legacy ROS2 publish-based control and is not used by the current MCP flow.

---

## Requirements

- Python 3.11+
- Network access to robot (`ROBOT_IP`)
- Node.js (only if using MCP Inspector)

Python dependencies are in `requirements.txt`:
- `mcp>=1.27.1`
- `unitree_webrtc_connect_leshy>=2.0.7`

---

## Installation

```bash
conda create -n go2_agent python=3.11
conda activate go2_agent
pip install -r requirements.txt
```

---

## Run server

Set robot IP:

```bash
export ROBOT_IP=192.168.123.161
```

Start MCP server:

```bash
python server.py
```

---

## Using MCP Inspector

Start Inspector:

```bash
npx @modelcontextprotocol/inspector
```

Then configure:

- Transport: `STDIO`
- Command: `python`
- Arguments: `/home/user/go2_agent/server.py` (replace with your path)
- Environment variable:
  - Key: `ROBOT_IP`
  - Value: robot IP (example `192.168.123.161`)

---

## MCP tools

### Connection / Debug

- `connect()`
- `disconnect()`
- `inspect_connection()`
- `inspect_datachannel()`
- `inspect_rtc_inner_req()`
- `inspect_pub_sub()`

### Direct motion

- `move(x=0, y=0, yaw=0, duration=0)`
- `stop()`

### Odometry / Pose

- `test_odom()`
- `get_position()`
- `get_orientation()`
- `get_pose()`
- `set_reference_pose()`
- `distance_from_reference()`
- `measure_distance_traveled()`
- `move_forward_distance(distance_meters, speed=0.4, timeout_s=20.0, tolerance_m=0.02)`
- `turn_degrees(degrees, yaw_speed=0.5, timeout_s=20.0, tolerance_deg=3.0)`

### LOW_STATE telemetry

- `test_low_state()`
- `get_imu()`
- `get_battery()`
- `get_motor_states()`
- `get_foot_forces()`

### Navigation manager

- `set_goal(x, y)`
- `get_navigation_state()`
- `start_navigation()`
- `stop_navigation()`
- `is_goal_reached()`
- `get_goal_status()`
- `cancel_goal()`

### Sport mode actions

- `list_sport_commands()`
- `execute_sport_command(command_name)`

---

## Navigation behavior summary

`NavigationManager` runs a background thread when started:

1. Reads current robot pose from odometry.
2. Computes distance and heading error to goal.
3. If heading error is large (>|10| deg), rotates in place.
4. Otherwise drives forward.
5. Stops and marks goal reached when within goal tolerance (default `0.15 m`).

This is a lightweight local navigator (not full SLAM/path planning).

---

## Typical workflow

1. `connect()`
2. Validate sensor feed:
   - `test_low_state()`
   - `test_odom()`
3. Manual checks:
   - `move(...)`, `stop()`
4. Start goal navigation:
   - `set_goal(x, y)`
   - `start_navigation()`
   - `get_goal_status()` / `is_goal_reached()`
5. End session:
   - `stop_navigation()`
   - `disconnect()`

---

## Important runtime notes

- Call `connect()` before any motion, telemetry, or navigation command.
- If odometry/low-state are not yet received, tools return informative messages.
- `disconnect()` stops navigation first, then closes WebRTC.
- `move()` includes a safety timeout mechanism via internal stop timer.

---

## Status

Current focus is robust MCP-driven robot operation with:
- navigation goals,
- closed-loop odometry primitives,
- and low-state observability.

Possible next steps:
- camera/vision integration,
- richer path planning,
- higher-level task agent behaviors.


-------------------
# Terminal 1 — set robot IP and start server
export ROBOT_IP=192.168.123.161
cd ~/Go2_agent_mcp
uvicorn client.app:app --host 0.0.0.0 --port 8000 --reload
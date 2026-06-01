# Go2 Agent MCP

MCP-based control server for Unitree Go2 using WebRTC.

This project recreates the core Go2 connection layer independently of DimOS and exposes robot control actions as MCP tools.

## Features

- Connect to Go2 through WebRTC
- Basic movement control
- Built-in sport command support (via Unitree `SPORT_CMD`)
- Stop robot movement
- Disconnect from robot
- MCP tool interface
- Tested on a real Unitree Go2

---

## Architecture

This project currently provides an MCP server only.

Since an MCP server does not provide a UI by itself, an MCP client is required to interact with it.

For development and testing this project uses MCP Inspector.

Architecture:

```text
MCP Inspector
      ↓
FastMCP Server
      ↓
Go2Controller
      ↓
UnitreeWebRTCConnection
      ↓
WebRTC DataChannel
      ↓
Unitree Go2
```

---

## Project Structure

```text
go2_agent/
│
├── server.py
├── requirements.txt
├── README.md
│
└── controllers/
    ├── go2_controller.py
    └── wireless_controller_old.py
```

---

## Installation

Create a new environment:

```bash
conda create -n go2_agent python=3.11
conda activate go2_agent
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Run MCP Server

Set your robot IP:

```bash
export ROBOT_IP=192.168.123.161
```

Start the server:

```bash
python server.py
```

The server will start and wait for an MCP client connection.

---

## Using MCP Inspector

Start MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

Open the generated URL in your browser.

Configure Inspector:

**Transport**

```text
STDIO
```

**Command**

```text
python
```

**Arguments**

```text
/home/user/go2_agent/server.py
```

Replace with your actual project path.

**Environment Variables**

Key:

```text
ROBOT_IP
```

Value:

```text
192.168.123.161
```

Click:

```text
Connect
```

---

## Available MCP Tools

```text
connect()
move(x, y, yaw, duration)
list_sport_commands()
execute_sport_command(command_name)
stop()
disconnect()
```

### Tool Behavior

- `connect()`
      - Initializes WebRTC connection to the robot using `ROBOT_IP`.
      - Must be called before movement or sport commands.
- `move(x, y, yaw, duration)`
      - Sends velocity-style joystick input.
      - If `duration > 0`, command is streamed repeatedly for that duration.
      - If `duration == 0`, sends a single movement command.
- `list_sport_commands()`
      - Returns the available sport command names from the Unitree sport API mapping.
- `execute_sport_command(command_name)`
      - Executes one sport action by command name (for example predefined motion actions supported by your robot firmware/library).
      - Returns an error string if command name is unknown or if not connected.
- `stop()`
      - Publishes zero movement values to halt motion.
- `disconnect()`
      - Stops movement and closes the WebRTC session.

---

## Example

Move robot forward:

```text
move(
    x=0,
    y=0.1,
    yaw=0,
    duration=1
)
```

List supported sport commands:

```text
list_sport_commands()
```

Run a sport command (replace with one from your list):

```text
execute_sport_command(command_name="StandUp")
```

## Available Sport Commands

The following sport commands are currently available through `list_sport_commands()`:

```text
Damp
BalanceStand
StopMove
StandUp
StandDown
RecoveryStand
Euler
Move
Sit
RiseSit
SwitchGait
Trigger
BodyHeight
FootRaiseHeight
SpeedLevel
Hello
Stretch
TrajectoryFollow
ContinuousGait
Content
Wallow
Dance1
Dance2
GetBodyHeight
GetFootRaiseHeight
GetSpeedLevel
SwitchJoystick
Pose
Scrape
FrontFlip
LeftFlip
RightFlip
BackFlip
FrontJump
FrontPounce
WiggleHips
GetState
EconomicGait
LeadFollow
FingerHeart
Bound
MoonWalk
OnesidedStep
CrossStep
Handstand
StandOut
FreeWalk
Standup
CrossWalk
```

### Commands Tested on Real Robot

Verified on hardware:

- `StandUp` / `Standup`
- `StandDown`
- `Hello`

---

## Current Status

Implemented:

- WebRTC connection to Go2
- MCP tool server
- Basic robot movement control
- Sport command discovery (`list_sport_commands`)
- Sport command execution (`execute_sport_command`)
- Real-robot validation for: `StandUp`/`Standup`, `StandDown`, `Hello`

Planned:

- StandUp / SitDown actions
- Additional robot actions
- Camera stream integration
- Agent support

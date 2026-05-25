# Go2 Agent MCP

MCP-based control server for Unitree Go2 using WebRTC.

This project recreates the core Go2 connection layer independently of DimOS and exposes robot control actions as MCP tools.

## Features

- Connect to Go2 through WebRTC
- Basic movement control
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
stop()
disconnect()
```

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

---

## Current Status

Implemented:

- WebRTC connection to Go2
- MCP tool server
- Basic robot movement control

Planned:

- StandUp / SitDown actions
- Additional robot actions
- Camera stream integration
- Agent support

import os
import asyncio
import threading
import time

from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD
from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection as LegionConnection,
    WebRTCConnectionMethod,
)


class Go2Controller:

    def __init__(self, ip: str | None = None):

        self.ip = ip or os.getenv("ROBOT_IP")

        self.conn = None
        self.loop = None
        self.thread = None
        self.task = None

        self.stop_timer = None
        self.cmd_vel_timeout = 0.2

        self.connection_ready = threading.Event()


    def connect(self) -> bool:

        if not self.ip:
            raise ValueError(
                "ROBOT_IP not found"
            )

        self.conn = LegionConnection(
            WebRTCConnectionMethod.LocalSTA,
            ip=self.ip
        )

        self.loop = asyncio.new_event_loop()

        async def async_connect():

            await self.conn.connect()

            await self.conn.datachannel.disableTrafficSaving(
                True
            )

            self.conn.datachannel.set_decoder(
                decoder_type="native"
            )

            self.connection_ready.set()

            while True:
                await asyncio.sleep(1)


        def start_background_loop():

            asyncio.set_event_loop(
                self.loop
            )

            self.task = self.loop.create_task(
                async_connect()
            )

            self.loop.run_forever()


        self.thread = threading.Thread(
            target=start_background_loop,
            daemon=True
        )

        self.thread.start()

        connected = self.connection_ready.wait(
            timeout=5
        )

        if connected:
            return "Connected to Go2"

        return "Connection timeout"


    def move(
        self,
        x: float = 0,
        y: float = 0,
        yaw: float = 0,
        duration: float = 0
    ) -> bool:

        if not self.conn:
            return False


        async def async_move():

            self.conn.datachannel.pub_sub.publish_without_callback(
                RTC_TOPIC["WIRELESS_CONTROLLER"],
                data={
                    "lx": -y,
                    "ly": x,
                    "rx": -yaw,
                    "ry": 0
                }
            )


        async def async_move_duration():

            start = time.time()

            while time.time() - start < duration:

                await async_move()

                await asyncio.sleep(
                    0.01
                )


        if self.stop_timer:
            self.stop_timer.cancel()


        self.stop_timer = threading.Timer(
            self.cmd_vel_timeout,
            self.stop
        )

        self.stop_timer.daemon = True
        self.stop_timer.start()


        try:

            if duration > 0:

                future = asyncio.run_coroutine_threadsafe(
                    async_move_duration(),
                    self.loop
                )

            else:

                future = asyncio.run_coroutine_threadsafe(
                    async_move(),
                    self.loop
                )

            future.result()

            return True

        except Exception as e:

            print(
                f"Move failed: {e}"
            )

            return False


    def stop(self):

        if not self.conn:
            return


        if self.stop_timer:

            self.stop_timer.cancel()

            self.stop_timer = None


        async def async_stop():

            self.conn.datachannel.pub_sub.publish_without_callback(
                RTC_TOPIC["WIRELESS_CONTROLLER"],
                data={
                    "lx": 0,
                    "ly": 0,
                    "rx": 0,
                    "ry": 0
                }
            )


        asyncio.run_coroutine_threadsafe(
            async_stop(),
            self.loop
        )


    def list_sport_commands(
        self
    ):

        return list(
            SPORT_CMD.keys()
        )

    def execute_sport_command(
        self,
        command_name: str
    ) -> str:

        if not self.conn:
            return "Not connected"

        api_id = SPORT_CMD.get(command_name)

        if api_id is None:
            return f"Unknown sport command: {command_name}"


        async def async_execute():

            await self.conn.datachannel.pub_sub.publish_request_new(
                RTC_TOPIC["SPORT_MOD"],
                options={
                    "api_id": api_id
                }
            )


        try:

            future = asyncio.run_coroutine_threadsafe(
                async_execute(),
                self.loop
            )

            future.result()

            return f"Sport command sent: {command_name}"

        except Exception as e:

            return f"Sport command failed: {e}"


    def disconnect(self):

        self.stop()

        async def async_disconnect():

            await self.conn.disconnect()


        asyncio.run_coroutine_threadsafe(
            async_disconnect(),
            self.loop
        )


        self.loop.call_soon_threadsafe(
            self.loop.stop
        )

        self.thread.join(
            timeout=5
        )
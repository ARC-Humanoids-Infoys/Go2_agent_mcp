import os
import asyncio
import threading
import time
import math
import numbers

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
        self.connection_error = None

        self.latest_low_state = None
        self.latest_odom = None
        self.latest_frame = None
        self._reference_pose = None


    def connect(self) -> bool:

        if not self.ip:
            raise ValueError(
                "ROBOT_IP not found"
            )

        self.conn = LegionConnection(
            WebRTCConnectionMethod.LocalSTA,
            ip=self.ip
        )

        self.connection_ready.clear()
        self.connection_error = None

        self.loop = asyncio.new_event_loop()

        async def async_connect():
            try:

                connect_task = asyncio.create_task(
                    self.conn.connect()
                )

                while not hasattr(self.conn, "video"):
                    if connect_task.done():
                        break
                    await asyncio.sleep(0.01)

                if hasattr(self.conn, "video"):
                    self.conn.video.add_track_callback(
                        self._video_callback
                    )

                await connect_task

                self.conn.video.switchVideoChannel(
                    True
                )

                await self.conn.datachannel.disableTrafficSaving(
                    True
                )

                self.conn.datachannel.set_decoder(
                    decoder_type="native"
                )

                self.conn.datachannel.pub_sub.subscribe(
                    RTC_TOPIC["LOW_STATE"],
                    self._on_low_state
                )

                self.conn.datachannel.pub_sub.subscribe(
                    RTC_TOPIC["ROBOTODOM"],
                    self._on_odom
                )

                self.connection_ready.set()

                while True:
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                raise

            except BaseException as e:
                self.connection_error = (
                    f"Connect failed: {e}"
                )
                self.connection_ready.set()
                self.conn = None


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
            if self.connection_error:
                return self.connection_error
            return "Connected to Go2"

        if self.task is not None:
            self.loop.call_soon_threadsafe(
                self.task.cancel
            )

        if self.conn:
            async def async_disconnect_timeout_cleanup():
                await self.conn.disconnect()

            try:
                future = asyncio.run_coroutine_threadsafe(
                    async_disconnect_timeout_cleanup(),
                    self.loop
                )
                future.result(timeout=2)
            except Exception:
                pass

        self.loop.call_soon_threadsafe(
            self.loop.stop
        )

        self.thread.join(
            timeout=2
        )

        self.conn = None
        self.loop = None
        self.thread = None
        self.task = None

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


    def _on_low_state(self, msg: dict):

        self.latest_low_state = msg.get("data", {})


    def _on_odom(self, msg: dict):

        if isinstance(msg, dict):
            self.latest_odom = msg.get("data", msg)
        else:
            self.latest_odom = msg


    async def _video_callback(self, track):

        while True:
            frame = await track.recv()
            self.latest_frame = frame


    def observe(
        self,
        save_path: str | None = None,
    ):

        if self.latest_frame is None:
            return "No frame available"

        frame = self.latest_frame
        img = frame.to_ndarray(format="bgr24")

        result = {
            "shape": list(img.shape),
            "saved": False,
        }

        if save_path:
            try:
                import cv2
                import os

                abs_path = os.path.abspath(save_path)
                ok = cv2.imwrite(abs_path, img)
                result["saved"] = bool(ok)
                result["save_path"] = abs_path
            except Exception as e:
                result["saved"] = False
                result["save_error"] = str(e)
        else:
            result["save_hint"] = "Provide save_path to save an image, e.g. /home/arc01/go2_agent/test.jpg"

        return result


    def _require_low_state(self):

        if not self.conn:
            return None, "Not connected"

        wait_timeout_s = 2.0
        start = time.time()

        while self.latest_low_state is None:
            if (time.time() - start) >= wait_timeout_s:
                break
            time.sleep(0.05)

        if self.latest_low_state is None:
            return None, "No LOW_STATE data received yet"

        return self.latest_low_state, None


    def _require_odom_state(self):

        if not self.conn:
            return None, "Not connected"

        wait_timeout_s = 2.0
        start = time.time()

        while self.latest_odom is None:
            if (time.time() - start) >= wait_timeout_s:
                break
            time.sleep(0.05)

        if self.latest_odom is None:
            return None, "No ROBOTODOM data received yet"

        return self.latest_odom, None


    def _extract_position(self, odom: dict) -> dict:

        def from_obj(obj):

            if isinstance(obj, dict):

                if "x" in obj and "y" in obj:
                    return {
                        "x": obj.get("x"),
                        "y": obj.get("y"),
                        "z": obj.get("z"),
                    }

                if "px" in obj and "py" in obj:
                    return {
                        "x": obj.get("px"),
                        "y": obj.get("py"),
                        "z": obj.get("pz"),
                    }

                for key in [
                    "position", "pose", "pos", "odom",
                    "state", "body", "base", "data"
                ]:
                    if key in obj:
                        found = from_obj(obj[key])
                        if found is not None:
                            return found

                for value in obj.values():
                    found = from_obj(value)
                    if found is not None:
                        return found

            if isinstance(obj, list):

                if (
                    len(obj) >= 2
                    and isinstance(obj[0], numbers.Number)
                    and isinstance(obj[1], numbers.Number)
                ):
                    return {
                        "x": obj[0],
                        "y": obj[1],
                        "z": obj[2] if len(obj) >= 3 else None,
                    }

                for item in obj:
                    found = from_obj(item)
                    if found is not None:
                        return found

            return None

        found = from_obj(odom)

        if found is not None:
            return found

        return {
            "x": None,
            "y": None,
            "z": None,
        }


    def _extract_orientation(self, odom: dict) -> dict:

        if not isinstance(odom, dict):
            return {
                "quaternion": None,
                "yaw_rad": None,
                "yaw_deg": None,
                "yaw": None,
            }

        quat = (
            odom.get("quaternion")
            or odom.get("quat")
            or odom.get("orientation")
            or odom.get("pose", {}).get("orientation") if isinstance(odom.get("pose"), dict) else None
        )

        yaw = None

        if "yaw" in odom:
            yaw = odom.get("yaw")
        elif "theta" in odom:
            yaw = odom.get("theta")

        if yaw is None and isinstance(odom.get("imu_state"), dict):
            rpy = odom.get("imu_state", {}).get("rpy", [])
            if len(rpy) >= 3:
                yaw = rpy[2]

        if not isinstance(yaw, numbers.Number):
            try:
                yaw = float(yaw)
            except Exception:
                yaw = None

        if yaw is None:
            yaw = self._yaw_from_quaternion(quat)

        yaw_deg = None
        if isinstance(yaw, numbers.Number):
            yaw_deg = math.degrees(float(yaw))

        return {
            "quaternion": quat,
            "yaw_rad": yaw,
            "yaw_deg": round(yaw_deg, 3) if yaw_deg is not None else None,
            "yaw": yaw,
        }


    def _yaw_from_quaternion(self, quat) -> float | None:

        if isinstance(quat, dict):
            x = quat.get("x")
            y = quat.get("y")
            z = quat.get("z")
            w = quat.get("w")
        elif isinstance(quat, list) and len(quat) >= 4:
            x, y, z, w = quat[0], quat[1], quat[2], quat[3]
        else:
            return None

        if None in (x, y, z, w):
            return None

        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)

        return math.atan2(siny_cosp, cosy_cosp)


    def _normalize_angle_rad(self, angle: float) -> float:

        while angle > math.pi:
            angle -= 2.0 * math.pi

        while angle < -math.pi:
            angle += 2.0 * math.pi

        return angle


    def _get_current_yaw(self) -> float | None:

        orientation = self.get_orientation()

        if isinstance(orientation, str):
            return None

        yaw = orientation.get("yaw_rad")

        if yaw is None:
            yaw = orientation.get("yaw")

        if isinstance(yaw, numbers.Number):
            return float(yaw)

        quat = orientation.get("quaternion")

        return self._yaw_from_quaternion(quat)


    def get_position(self) -> dict | str:

        odom, err = self._require_odom_state()

        if err:
            return err

        return self._extract_position(odom)


    def get_orientation(self) -> dict | str:

        odom, err = self._require_odom_state()

        if err:
            return err

        return self._extract_orientation(odom)


    def get_pose(self) -> dict | str:

        odom, err = self._require_odom_state()

        if err:
            return err

        return {
            "position": self._extract_position(odom),
            "orientation": self._extract_orientation(odom),
            "raw": odom,
        }


    def set_reference_pose(self) -> dict | str:

        pose = self.get_pose()

        if isinstance(pose, str):
            return pose

        position = pose.get("position", {})

        if position.get("x") is None or position.get("y") is None:
            return "Reference pose not set: odometry position x/y missing. Run test_odom() and verify ROBOTODOM payload"

        self._reference_pose = pose

        return {
            "status": "Reference pose set",
            "position": pose.get("position"),
        }


    def distance_from_reference(self) -> dict | str:

        if self._reference_pose is None:
            return "Reference pose is not set. Call set_reference_pose() first"

        current = self.get_position()

        if isinstance(current, str):
            return current

        reference = self._reference_pose.get("position", {})

        x0 = reference.get("x")
        y0 = reference.get("y")
        x1 = current.get("x")
        y1 = current.get("y")

        if None in (x0, y0, x1, y1):
            return "Could not compute distance from reference (missing x/y)"

        distance = math.sqrt(
            (x1 - x0) ** 2 +
            (y1 - y0) ** 2
        )

        return {
            "distance_m": round(distance, 4),
            "reference": {
                "x": x0,
                "y": y0,
            },
            "current": {
                "x": x1,
                "y": y1,
            }
        }


    def measure_distance_traveled(self) -> dict | str:

        return self.distance_from_reference()


    def move_forward_distance(
        self,
        distance_meters: float,
        speed: float = 0.4,
        timeout_s: float = 20.0,
        tolerance_m: float = 0.02,
    ) -> dict | str:

        if not self.conn:
            return "Not connected"

        if distance_meters <= 0:
            return "distance_meters must be > 0"

        if speed <= 0:
            return "speed must be > 0"

        ref_result = self.set_reference_pose()

        if isinstance(ref_result, str):
            return ref_result

        start_time = time.time()
        target = distance_meters
        last_distance = 0.0

        try:

            while True:

                elapsed = time.time() - start_time

                if elapsed > timeout_s:
                    self.stop()
                    return {
                        "status": "timeout",
                        "target_m": round(target, 4),
                        "distance_m": round(last_distance, 4),
                        "elapsed_s": round(elapsed, 3),
                    }

                dist_info = self.distance_from_reference()

                if isinstance(dist_info, str):
                    self.stop()
                    return dist_info

                current_distance = dist_info.get("distance_m", 0)
                last_distance = current_distance

                if current_distance >= (target - tolerance_m):
                    self.stop()
                    return {
                        "status": "reached",
                        "target_m": round(target, 4),
                        "distance_m": round(current_distance, 4),
                        "elapsed_s": round(elapsed, 3),
                    }

                move_ok = self.move(
                    x=speed,
                    y=0,
                    yaw=0,
                    duration=0,
                )

                if not move_ok:
                    self.stop()
                    return "Movement failed during closed-loop control"

                time.sleep(0.05)

        finally:
            self.stop()


    def turn_degrees(
        self,
        degrees: float,
        yaw_speed: float = 0.5,
        timeout_s: float = 20.0,
        tolerance_deg: float = 3.0,
    ) -> dict | str:

        if not self.conn:
            return "Not connected"

        if degrees == 0:
            return {
                "status": "no-op",
                "target_deg": 0.0,
                "turned_deg": 0.0,
            }

        if yaw_speed <= 0:
            return "yaw_speed must be > 0"

        start_yaw = self._get_current_yaw()

        if start_yaw is None:
            return "Could not read yaw from odometry"

        target_delta = math.radians(degrees)
        target_yaw = self._normalize_angle_rad(
            start_yaw + target_delta
        )

        tolerance_rad = math.radians(abs(tolerance_deg))
        start_time = time.time()

        last_error = None

        try:

            while True:

                elapsed = time.time() - start_time

                if elapsed > timeout_s:
                    self.stop()
                    turned = None
                    current_yaw = self._get_current_yaw()
                    if current_yaw is not None:
                        turned = math.degrees(
                            self._normalize_angle_rad(
                                current_yaw - start_yaw
                            )
                        )
                    return {
                        "status": "timeout",
                        "target_deg": round(degrees, 3),
                        "turned_deg": round(turned, 3) if turned is not None else None,
                        "remaining_error_deg": round(math.degrees(last_error), 3) if last_error is not None else None,
                        "elapsed_s": round(elapsed, 3),
                    }

                current_yaw = self._get_current_yaw()

                if current_yaw is None:
                    self.stop()
                    return "Could not read yaw from odometry during turn"

                error = self._normalize_angle_rad(
                    target_yaw - current_yaw
                )
                last_error = error

                if abs(error) <= tolerance_rad:
                    self.stop()
                    turned = math.degrees(
                        self._normalize_angle_rad(
                            current_yaw - start_yaw
                        )
                    )
                    return {
                        "status": "reached",
                        "target_deg": round(degrees, 3),
                        "turned_deg": round(turned, 3),
                        "remaining_error_deg": round(math.degrees(error), 3),
                        "elapsed_s": round(elapsed, 3),
                    }

                cmd_sign = 1.0 if error > 0 else -1.0

                move_ok = self.move(
                    x=0,
                    y=0,
                    yaw=cmd_sign * yaw_speed,
                    duration=0,
                )

                if not move_ok:
                    self.stop()
                    return "Movement failed during closed-loop turn"

                time.sleep(0.05)

        finally:
            self.stop()


    def get_imu(self) -> dict | str:

        state, err = self._require_low_state()

        if err:
            return err

        rpy = state.get("imu_state", {}).get("rpy", [])

        return {
            "roll":  round(rpy[0], 6) if len(rpy) > 0 else None,
            "pitch": round(rpy[1], 6) if len(rpy) > 1 else None,
            "yaw":   round(rpy[2], 6) if len(rpy) > 2 else None,
        }


    def get_battery(self) -> dict | str:

        state, err = self._require_low_state()

        if err:
            return err

        bms = state.get("bms_state", {})

        return {
            "soc_percent":    bms.get("soc"),
            "voltage_v":      round(state.get("power_v", 0), 3),
            "current_ma":     bms.get("current"),
            "cycle_count":    bms.get("cycle"),
            "bq_ntc_temp_c":  bms.get("bq_ntc"),
            "mcu_ntc_temp_c": bms.get("mcu_ntc"),
        }


    def get_motor_states(self) -> list | str:

        state, err = self._require_low_state()

        if err:
            return err

        motors = state.get("motor_state", [])

        leg_names = [
            "FR_hip", "FR_thigh", "FR_calf",
            "FL_hip", "FL_thigh", "FL_calf",
            "RR_hip", "RR_thigh", "RR_calf",
            "RL_hip", "RL_thigh", "RL_calf",
        ]

        result = []

        for i, motor in enumerate(motors[:12]):

            result.append({
                "id":          i,
                "name":        leg_names[i],
                "q_rad":       round(motor.get("q", 0), 6),
                "temp_c":      motor.get("temperature"),
                "lost":        motor.get("lost"),
            })

        return result


    def get_foot_forces(self) -> dict | str:

        state, err = self._require_low_state()

        if err:
            return err

        forces = state.get("foot_force", [])

        labels = ["FR", "FL", "RR", "RL"]

        return {
            labels[i]: forces[i]
            for i in range(len(forces))
        }


    def test_low_state(self) -> str:

        state, err = self._require_low_state()

        if err:
            return err

        return str(state)


    def test_odom(self) -> str:

        odom, err = self._require_odom_state()

        if err:
            return err

        return str(odom)


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

        if not self.loop or not self.thread:
            self.conn = None
            self.connection_ready.clear()
            self.connection_error = None
            return

        if self.task is not None:
            self.loop.call_soon_threadsafe(
                self.task.cancel
            )

        if self.conn:
            async def async_disconnect():
                await self.conn.disconnect()

            try:
                future = asyncio.run_coroutine_threadsafe(
                    async_disconnect(),
                    self.loop
                )
                future.result(timeout=3)
            except Exception:
                pass

        self.loop.call_soon_threadsafe(
            self.loop.stop
        )

        self.thread.join(
            timeout=5
        )

        self.conn = None
        self.loop = None
        self.thread = None
        self.task = None
        self.latest_low_state = None
        self.latest_odom = None
        self.latest_frame = None
        self.connection_ready.clear()
        self.connection_error = None
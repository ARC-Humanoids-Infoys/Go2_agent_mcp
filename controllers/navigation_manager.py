import math
import threading
import time


class NavigationManager:

    def __init__(self, controller, goal_tolerance_m: float = 0.15):

        self.controller = controller

        self.current_goal = None
        self.state = "IDLE"
        self.goal_reached = False
        self.goal_tolerance_m = goal_tolerance_m

        self.running = False
        self._thread = None
        self._lock = threading.Lock()


    def _normalize_angle_rad(self, angle: float) -> float:

        while angle > math.pi:
            angle -= 2.0 * math.pi

        while angle < -math.pi:
            angle += 2.0 * math.pi

        return angle


    def set_goal(self, x: float, y: float) -> dict:

        with self._lock:

            self.current_goal = {
                "position": {
                    "x": x,
                    "y": y,
                }
            }

            self.state = "FOLLOWING_PATH"
            self.goal_reached = False

        return {
            "status": "goal_set",
            "goal": self.current_goal,
            "state": self.state,
        }


    def cancel_goal(self) -> dict:

        with self._lock:
            self.current_goal = None
            self.state = "IDLE"
            self.goal_reached = False

        self.controller.stop()

        return {
            "status": "goal_cancelled",
            "state": self.state,
        }


    def get_navigation_state(self) -> dict:

        with self._lock:
            state = self.state
            current_goal = self.current_goal

        return {
            "state": state,
            "current_goal": current_goal,
            "goal_tolerance_m": self.goal_tolerance_m,
            "running": self.running,
        }


    def is_goal_reached(self) -> dict:

        with self._lock:
            goal_reached = self.goal_reached

        return {
            "goal_reached": goal_reached,
        }


    def start(self) -> dict:

        if self.running:
            return {
                "status": "already_running",
            }

        self.running = True
        self._thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
        )
        self._thread.start()

        return {
            "status": "started",
        }


    def stop(self) -> dict:

        self.running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        self.controller.stop()

        return {
            "status": "stopped",
        }


    def _worker_loop(self):

        while self.running:

            with self._lock:
                following = self.state == "FOLLOWING_PATH"

            if not following:
                time.sleep(0.1)
                continue

            status = self.get_goal_status()

            distance = status.get("distance_to_goal")
            heading_error_deg = status.get("heading_error_deg")
            goal_reached = status.get("goal_reached", False)

            if distance is None or heading_error_deg is None:
                self.controller.stop()
                time.sleep(0.1)
                continue

            if goal_reached:

                self.controller.stop()

                with self._lock:
                    self.state = "IDLE"
                    self.goal_reached = True

                time.sleep(0.1)
                continue

            if abs(heading_error_deg) > 10.0:

                yaw_cmd = 0.4 if heading_error_deg > 0 else -0.4

                self.controller.move(
                    x=0,
                    y=0,
                    yaw=yaw_cmd,
                    duration=0,
                )

            else:

                self.controller.move(
                    x=0.3,
                    y=0,
                    yaw=0,
                    duration=0,
                )

            time.sleep(0.05)


    def get_goal_status(self) -> dict:

        with self._lock:
            current_goal = self.current_goal
            state = self.state

        if current_goal is None:
            with self._lock:
                self.goal_reached = False
            return {
                "state": state,
                "goal_reached": False,
                "distance_to_goal": None,
                "target_heading": None,
                "target_heading_deg": None,
                "current_heading": None,
                "current_heading_deg": None,
                "heading_error": None,
                "heading_error_deg": None,
                "message": "No active goal",
            }

        position = self.controller.get_position()

        if isinstance(position, str):
            with self._lock:
                goal_reached = self.goal_reached
            return {
                "state": state,
                "goal_reached": goal_reached,
                "distance_to_goal": None,
                "target_heading": None,
                "target_heading_deg": None,
                "current_heading": None,
                "current_heading_deg": None,
                "heading_error": None,
                "heading_error_deg": None,
                "message": position,
            }

        x = position.get("x")
        y = position.get("y")
        gx = current_goal["position"].get("x")
        gy = current_goal["position"].get("y")

        if None in (x, y, gx, gy):
            with self._lock:
                goal_reached = self.goal_reached
            return {
                "state": state,
                "goal_reached": goal_reached,
                "distance_to_goal": None,
                "target_heading": None,
                "target_heading_deg": None,
                "current_heading": None,
                "current_heading_deg": None,
                "heading_error": None,
                "heading_error_deg": None,
                "message": "Missing x/y in current pose or goal",
            }

        dx = gx - x
        dy = gy - y

        distance_to_goal = math.sqrt(
            dx ** 2 + dy ** 2
        )

        target_heading = math.atan2(dy, dx)

        current_heading = self.controller._get_current_yaw()

        if current_heading is None:
            with self._lock:
                goal_reached = self.goal_reached
            return {
                "state": state,
                "goal": current_goal,
                "current_position": {
                    "x": x,
                    "y": y,
                },
                "distance_to_goal": round(distance_to_goal, 4),
                "target_heading": round(target_heading, 6),
                "target_heading_deg": round(math.degrees(target_heading), 3),
                "current_heading": None,
                "current_heading_deg": None,
                "heading_error": None,
                "heading_error_deg": None,
                "goal_tolerance_m": self.goal_tolerance_m,
                "goal_reached": goal_reached,
                "message": "Could not read current robot heading",
            }

        heading_error = self._normalize_angle_rad(
            target_heading - current_heading
        )

        with self._lock:
            self.goal_reached = distance_to_goal <= self.goal_tolerance_m
            goal_reached = self.goal_reached

        return {
            "state": state,
            "goal": current_goal,
            "current_position": {
                "x": x,
                "y": y,
            },
            "distance_to_goal": round(distance_to_goal, 4),
            "target_heading": round(target_heading, 6),
            "target_heading_deg": round(math.degrees(target_heading), 3),
            "current_heading": round(current_heading, 6),
            "current_heading_deg": round(math.degrees(current_heading), 3),
            "heading_error": round(heading_error, 6),
            "heading_error_deg": round(math.degrees(heading_error), 3),
            "goal_tolerance_m": self.goal_tolerance_m,
            "goal_reached": goal_reached,
        }

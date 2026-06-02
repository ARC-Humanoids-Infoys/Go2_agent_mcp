import math


class NavigationManager:

    def __init__(self, controller, goal_tolerance_m: float = 0.15):

        self.controller = controller

        self.current_goal = None
        self.state = "IDLE"
        self.goal_reached = False
        self.goal_tolerance_m = goal_tolerance_m


    def _normalize_angle_rad(self, angle: float) -> float:

        while angle > math.pi:
            angle -= 2.0 * math.pi

        while angle < -math.pi:
            angle += 2.0 * math.pi

        return angle


    def set_goal(self, x: float, y: float) -> dict:

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

        self.current_goal = None
        self.state = "IDLE"
        self.goal_reached = False

        return {
            "status": "goal_cancelled",
            "state": self.state,
        }


    def get_navigation_state(self) -> dict:

        return {
            "state": self.state,
            "current_goal": self.current_goal,
            "goal_tolerance_m": self.goal_tolerance_m,
        }


    def is_goal_reached(self) -> dict:

        return {
            "goal_reached": self.goal_reached,
        }


    def get_goal_status(self) -> dict:

        if self.current_goal is None:
            self.goal_reached = False
            return {
                "state": self.state,
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
            return {
                "state": self.state,
                "goal_reached": self.goal_reached,
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
        gx = self.current_goal["position"].get("x")
        gy = self.current_goal["position"].get("y")

        if None in (x, y, gx, gy):
            return {
                "state": self.state,
                "goal_reached": self.goal_reached,
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
            return {
                "state": self.state,
                "goal": self.current_goal,
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
                "goal_reached": self.goal_reached,
                "message": "Could not read current robot heading",
            }

        heading_error = self._normalize_angle_rad(
            target_heading - current_heading
        )

        self.goal_reached = distance_to_goal <= self.goal_tolerance_m

        return {
            "state": self.state,
            "goal": self.current_goal,
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
            "goal_reached": self.goal_reached,
        }

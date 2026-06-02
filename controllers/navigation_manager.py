class NavigationManager:

    def __init__(self):

        self.current_goal = None
        self.state = "IDLE"
        self.goal_reached = False


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
        }


    def is_goal_reached(self) -> dict:

        return {
            "goal_reached": self.goal_reached,
        }

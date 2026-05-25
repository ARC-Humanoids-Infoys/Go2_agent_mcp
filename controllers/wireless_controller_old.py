import subprocess
from typing import Any


class WirelessController:
    def __init__(
        self,
        topic: str = "/wirelesscontroller",
        msg_type: str = "unitree_go/msg/WirelessController",
        setup_sh_path: str = "",
    ):
        self.topic = topic
        self.msg_type = msg_type
        self.rate = 10
        self.setup_sh_path = setup_sh_path

    def execute(self, command: str):

        try:

            result = subprocess.run(
                command,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return False, result.stderr

            return True, result.stdout

        except Exception as exc:
            return False, str(exc)

    def publish(
        self,
        lx: float,
        ly: float,
        rx: float,
        ry: float,
        keys: int,
        duration: float = 0,
    ) -> tuple[bool, Any]:
        if self.rate > 0 and duration > 0:
            t = int(self.rate * duration)
            rate_opt = f"-r {self.rate} --times {t}"
        else:
            rate_opt = "-1"

        setup_cmd = f"source {self.setup_sh_path} && " if self.setup_sh_path else ""
        command = (
            f"{setup_cmd}ros2 topic pub {self.topic} {self.msg_type} "
            f"'{{lx: {lx}, ly: {ly}, rx: {rx}, ry: {ry}, keys: {keys}}}' {rate_opt}"
        )
        return self.execute(command)

    def _customised_movements(self, keys: int, rate: int | None = None, times: int = 5) -> tuple[bool, Any]:
        rate = rate if rate is not None else self.rate
        rate_opt = f"-r {rate} --times {times}"
        setup_cmd = f"source {self.setup_sh_path} && " if self.setup_sh_path else ""
        command = (
            f"{setup_cmd}ros2 topic pub {self.topic} {self.msg_type} "
            f"'{{lx: 0.0, ly: 0.0, rx: 0.0, ry: 0.0, keys: {keys}}}' {rate_opt}"
        )
        return self.execute(command)

    def stand_up_from_a_fall(self) -> tuple[bool, Any]:
        return self._customised_movements(keys=1056)

    def shake_hands(self):
        success, msg = self.stand_up_from_a_fall()
        if not success:
            return False, msg
        return self._customised_movements(keys=528)

    def stop(self) -> tuple[bool, Any]:
        return self._customised_movements(keys=0, times=3)

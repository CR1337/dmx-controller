import json
import sched
import time
import sys
from typing import Dict

from ftdi_dmx_interface import FtdiDmxInterface


Program = Dict[float, Dict[int, int]]


class DmxController:

    _interface: FtdiDmxInterface
    _program: Program | None
    _scheduler: sched.scheduler

    def __init__(self):
        self._interface = FtdiDmxInterface()
        self._program = None
        self._scheduler = sched.scheduler(time.time, time.sleep)

    def __del__(self):
        self._interface.stop()

    def load(self, program: Program | str):
        if isinstance(program, str):
            with open(program, 'r') as file:
                program = json.load(file)

        self._program = {
            float(t): {
                int(channel): int(value)
                for channel, value in frame.items()
            }
            for t, frame in program.items()
        }

    def run(self):
        if self._program is None:
            raise RuntimeError("No program loaded.")

        for i, (delay, data) in enumerate(self._program.items()):
            self._scheduler.enter(delay, i, self._scheduler_callback, (data,))

        self._scheduler.run()
        self._interface.stop()

    def _scheduler_callback(self, data: Dict[int, int]):
        for channel, value in data.items():
            self._interface[channel] = value
        self._interface.render()


if __name__ == "__main__":
    filename = sys.argv[1]
    c = DmxController()
    c.load(filename)
    c.run()

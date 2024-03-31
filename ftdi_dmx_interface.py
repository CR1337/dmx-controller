from pylibftdi import Device
from ctypes import cdll, c_long, byref, Structure
from typing import List, Tuple


class Timespec(Structure):
    _fields_ = [
        ("seconds", c_long),
        ("nanoseconds", c_long)
    ]


class FtdiDmxInterface:

    LIBC = cdll.LoadLibrary("libc.so.6")
    MS_PER_S: int = 1_000_000
    NS_PER_MS: int = 1_000
    US_PER_MS: int = 1_000

    BAUDRATE: int = 250_000

    BITS_8: int = 8
    STOP_BITS_2: int = 2
    PARITY_NONE: int = 0
    BREAK_OFF: int = 0
    BREAK_ON: int = 1

    CHANNEL_RANGE: Tuple[int, int] = (1, 512)
    VALUE_RANGE: Tuple[int, int] = (0, 255)

    @classmethod
    def _wait_us(cls, microseconds: int):
        sleep_time = Timespec(
            seconds=microseconds // cls.MS_PER_S,
            nanoseconds=(microseconds % cls.MS_PER_S) * cls.NS_PER_MS
        )
        cls.LIBC.nanosleep(byref(sleep_time), byref(Timespec()))

    @classmethod
    def _wait_ms(cls, milliseconds: int):
        cls._wait_us(milliseconds * cls.US_PER_MS)

    _ftdi_device: Device
    _dmx_channels: List[int]
    _highest_updated_channel: int

    def __init__(self):
        self._ftdi_device = Device()
        self._ftdi_device.ftdi_fn.ftdi_set_baudrate(self.BAUDRATE)
        self._ftdi_device.ftdi_fn.ftdi_set_line_property(
            self.BITS_8, self.STOP_BITS_2, self.PARITY_NONE
        )
        self.blackout()

    def __del__(self):
        self.blackout()
        self._ftdi_device.close()

    def reset(self):
        self._dmx_channels = [0] * (self.CHANNEL_RANGE[-1] + 1)
        self._highest_updated_channel = self.CHANNEL_RANGE[-1]

    def set_channel(self, channel: int, value: int):
        if not (self.CHANNEL_RANGE[0] <= channel <= self.CHANNEL_RANGE[-1]):
            raise ValueError(f"Channel {channel} out of range.")
        if not (self.VALUE_RANGE[0] <= value <= self.VALUE_RANGE[-1]):
            raise ValueError(f"Value {value} out of range.")

        self._dmx_channels[channel] = value
        self._highest_updated_channel = max(
            self._highest_updated_channel, channel
        )

    def get_channel(self, channel: int) -> int:
        if not (self.CHANNEL_RANGE[0] <= channel <= self.CHANNEL_RANGE[-1]):
            raise ValueError(f"Channel {channel} out of range.")

        return self._dmx_channels[channel]

    def __setitem__(self, key: int, value: int):
        self.set_channel(key, value)

    def __getitem__(self, key: int) -> int:
        return self.get_channel(key)

    def blackout(self):
        self.reset()
        self.render()

    def render(self):
        data = bytes(self._dmx_channels[:self._highest_updated_channel + 1])

        self._ftdi_device.ftdi_fn.ftdi_set_line_property2(
            self.BITS_8, self.STOP_BITS_2, self.PARITY_NONE, self.BREAK_ON
        )
        self._wait_us(96)
        self._ftdi_device.ftdi_fn.ftdi_set_line_property2(
            self.BITS_8, self.STOP_BITS_2, self.PARITY_NONE, self.BREAK_OFF
        )
        self._wait_us(8)
        self._ftdi_device.write(data)
        self._wait_ms(2)

        self._highest_updated_channel = 0


if __name__ == "__main__":
    dmx = FtdiDmxInterface()

    dmx[1] = 255
    dmx[9] = 255
    dmx.render()

    import time
    from itertools import count

    for i in count():
        dmx[2] = i % 256
        dmx[10] = 255 - (i % 256)
        dmx.render()
        time.sleep(0.01)

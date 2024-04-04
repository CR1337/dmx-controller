import struct
import sys
import json
from typing import Dict


class JsonToDmx:

    _output_filename: str
    _data: Dict[float, Dict[int, int]]

    def __init__(self, input_filename: str, output_filename: str):
        self._output_filename = output_filename

        with open(input_filename, 'r') as file:
            data = json.load(file)
        self._data = {
            float(t): {
                int(channel): int(value)
                for channel, value in frame.items()
            }
            for t, frame in data.items()
        }

    def convert(self):
        size = 8
        for t, frame in self._data.items():
            size += 6
            size += 3 * len(frame)

        buffer = bytearray(size)
        offset = 0
        struct.pack_into(">4s", buffer, offset, b"DMX ")
        offset = 4
        struct.pack_into("<I", buffer, offset, len(self._data))
        offset = 8

        for t, frame in self._data.items():
            struct.pack_into("<fH", buffer, offset, t, len(frame))
            offset += 6
            for channel, value in frame.items():
                struct.pack_into("<HB", buffer, offset, channel, value)
                offset += 3

        with open(self._output_filename, 'wb') as file:
            file.write(buffer)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Wrong number of arguments.")
        exit(1)

    input_filename = sys.argv[1]

    if len(sys.argv) == 2:
        output_filename = f"{input_filename}.dmx"
    else:
        output_filename = sys.argv[2]

    converter = JsonToDmx(input_filename, output_filename)
    converter.convert()

from __future__ import annotations
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from itertools import groupby
from typing import Any, Dict, List, Set, Tuple


class Segment:
    _start_time: int
    _end_time: int
    _start_values: List[int]
    _end_values: List[int]

    _zero_length: bool
    _ms: List[float]
    _ns: List[float]

    @property
    def end_time(self) -> int:
        return self._end_time

    def __init__(
        self,
        start_time: int, end_time: int,
        start_values: Dict[int, int], end_values: Dict[int, int]
    ):
        self._start_time = start_time
        self._end_time = end_time

        self._start_values = [start_values.get(i, 0) for i in range(0, 513)]
        self._end_values = [end_values.get(i, 0) for i in range(0, 513)]

        if self._end_time == self._start_time:
            self._zero_length = True
        else:
            self._zero_length = False

            self._ms = [
                (e - s) / (self._end_time - self._start_time)
                for s, e in zip(self._start_values, self._end_values)
            ]
            self._ns = [
                e - m * self._end_time
                for e, m in zip(self._end_values, self._ms)
            ]

    def get_value(self, t: int, channel: int) -> int:
        if self._zero_length:
            return self._start_values[channel]
        else:
            return min(max(int(
                self._ms[channel] * t + self._ns[channel]
            ), 0), 255)


@dataclass
class Fixture:
    id_: int
    address: int


@dataclass
class ShowFunction:
    id_: int
    start_time: int
    duration: int


@dataclass
class Sequence:
    show_function: ShowFunction
    steps: List[Step]

    TIME_RESOLUTION: int = 5  # ms

    def serialize_data(
        self, fixtures: List[Fixture]
    ) -> Dict[float, Dict[int, int]]:
        segments: List[Segment] = []
        channels: Set[int] = set()

        start_time = self.show_function.start_time

        step = self.steps[0]
        channels |= step.data.keys()
        segments.append(Segment(
            start_time,
            start_time + step.fade_in,
            {},
            step.data
        ))  # fade in
        segments.append(Segment(
            start_time + step.fade_in,
            start_time + step.fade_in + step.hold,
            step.data,
            step.data
        ))  # hold
        segments.append(Segment(
            start_time + step.fade_in + step.hold,
            start_time + step.fade_in + step.hold + step.fade_out,
            step.data,
            {} if len(self.steps) == 1 else self.steps[1].data
        ))  # fade out

        for i, step in enumerate(self.steps[1:-1], start=1):
            channels |= step.data.keys()
            segments.append(Segment(
                segments[-1].end_time,
                segments[-1].end_time + step.fade_in,
                self.steps[i - 1].data,
                step.data
            ))
            segments.append(Segment(
                segments[-1].end_time,
                segments[-1].end_time + step.hold,
                step.data,
                step.data
            ))
            segments.append(Segment(
                segments[-1].end_time,
                segments[-1].end_time + step.fade_out,
                step.data,
                self.steps[i + 1].data
            ))

        if len(self.steps) > 1:
            step = self.steps[-1]
            channels |= step.data.keys()
            segments.append(Segment(
                segments[-1].end_time,
                segments[-1].end_time + step.fade_in,
                self.steps[-2].data,
                step.data
            ))
            segments.append(Segment(
                segments[-1].end_time,
                segments[-1].end_time + step.hold,
                step.data,
                step.data
            ))
            segments.append(Segment(
                segments[-1].end_time,
                segments[-1].end_time + step.fade_out,
                step.data,
                {}
            ))

        result = {}
        done = False
        current_segment_idx = 0
        for t in range(
            self.show_function.start_time,
            self.show_function.start_time + self.show_function.duration,
            self.TIME_RESOLUTION
        ):
            while segments[current_segment_idx].end_time <= t:
                current_segment_idx += 1
                if current_segment_idx == len(segments):
                    done = True
                    break

            if done:
                break

            result[t / 1000] = {
                channel: segments[current_segment_idx].get_value(t, channel)
                for channel in channels
            }

        result[max(result) + self.TIME_RESOLUTION / 1000] = {
            channel: 0 for channel in channels
        }

        return result


@dataclass
class Step:
    fade_in: int
    hold: int
    fade_out: int
    data: Dict[int, int]


class QxwConverter:

    _input_filename: str
    _output_filename: str

    _fixtures: Dict[int, Fixture]
    _sequences: Dict[int, Sequence]
    _serialized_data: Dict[float, Dict[int, int]]
    _compressed_serialized_data: Dict[float, Dict[int, int]]

    def __init__(self, input_filename: str, output_filename: str):
        self._input_filename = input_filename
        self._output_filename = output_filename

        self._fixtures = {}
        self._sequences = {}

    def convert(self):
        root = ET.parse(self._input_filename).getroot()
        self._parse_fixtures_and_functions(root)
        self._serialize()
        self._compress()
        with open(self._output_filename, 'w') as file:
            json.dump(self._compressed_serialized_data, file)

    @staticmethod
    def make_pairs(container: List[Any]) -> List[Tuple[Any, Any]]:
        return [
            (container[i], container[i + 1])
            for i in range(0, len(container), 2)
        ]

    def _parse_fixtures(
        self, fixture_tags: List[ET.Element]
    ) -> Dict[int, Fixture]:
        return {
            fixture.id_: fixture
            for fixture in (
                Fixture(
                    id_=int(tag.find("{*}ID").text),
                    address=int(tag.find("{*}Address").text)
                )
                for tag in fixture_tags
            )
        }

    def _parse_show_functions(
        self,
        function_tags: Dict[str, ET.Element],
        show_selection: int
    ) -> Dict[int, ShowFunction]:
        track_tags = function_tags['Show'][show_selection].findall("{*}Track")
        show_function_tags = []
        for track_tag in track_tags:
            show_function_tags += track_tag.findall("{*}ShowFunction")
        return {
            show_function.id_: show_function
            for show_function in (
                ShowFunction(
                    id_=int(tag.get('ID')),
                    start_time=int(tag.get('StartTime')),
                    duration=int(tag.get('Duration'))
                )
                for tag in show_function_tags
            )
        }

    def _parse_sequences(
        self,
        grouped_function_tags: Dict[str, ET.Element],
        show_functions: Dict[int, ShowFunction]
    ) -> Dict[int, Sequence]:
        return {
            sequence.show_function.id_: sequence
            for sequence in (
                Sequence(
                    show_function=show_functions[int(tag.get('ID'))],
                    steps=self._parse_steps(tag)
                )
                for tag in grouped_function_tags['Sequence']
                if int(tag.get('ID')) in show_functions
            )
            if len(sequence.steps) > 0
        }

    # def _parse_step(self, tag: ET.Element) -> Step:
    #     speed_tag = tag.find("{*}Speed")
    #     fixture_val_tag = tag.find("{*}FixtureVal")
    #     fixture_id = int(fixture_val_tag.get('ID'))
    #     fixture_offset = self._fixtures[fixture_id].address
    #     raw_data = [int(x) for x in fixture_val_tag.text.split(",")]
    #     data = {
    #         (int(channel) + fixture_offset) + 1: int(value)
    #         for channel, value in self.make_pairs(raw_data)
    #     }
    #     return Step(
    #         fade_in=int(speed_tag.get('FadeIn')),
    #         hold=int(speed_tag.get('Duration')),
    #         fade_out=int(speed_tag.get('FadeOut')),
    #         data=data
    #     )

    def _parse_steps(self, tag: ET.Element) -> List[Step]:
        step_tags = tag.findall("{*}Step")

        if len(step_tags) > 1:
            return [
                Step(
                    fade_in=int(tag.get('FadeIn')),
                    hold=int(tag.get('Hold')),
                    fade_out=int(tag.get('FadeOut')),
                    data=self._parse_step_data(tag.text)
                )
                for tag in step_tags
                if tag.text is not None
            ]

        elif len(step_tags) == 1:  # weird special case
            speed_tag = tag.find("{*}Speed")
            fade_in = int(speed_tag.get('FadeIn'))
            fade_out = int(speed_tag.get('FadeOut'))
            duration = int(speed_tag.get('Duration'))
            return [
                Step(
                    fade_in=fade_in,
                    hold=duration - fade_in,
                    fade_out=fade_out,
                    data=self._parse_step_data(step_tags[0].text)
                )
            ]

        else:
            return []

    def _parse_step_data(self, raw_data: str) -> Dict[int, int]:
        return {
            (int(channel) + 1 + self._fixtures[int(fixture_id)].address):
            int(value)
            for fixture_id, csv_data in self.make_pairs(raw_data.split(":"))
            for channel, value in self.make_pairs(csv_data.split(","))
        }

    def _parse_fixtures_and_functions(self, root: ET.Element):
        engine_tag = root.find("{*}Engine")
        fixture_tags = engine_tag.findall("{*}Fixture")
        function_tags = engine_tag.findall("{*}Function")

        def group_key(element: ET.Element) -> str:
            return element.get('Type')

        function_tags.sort(key=group_key)
        grouped_function_tags = {
            key: list(group)
            for key, group
            in groupby(function_tags, key=group_key)
        }

        self._fixtures = self._parse_fixtures(fixture_tags)

        if len(grouped_function_tags['Show']) < 1:
            print("No show defined.")
            exit(0)
        elif len(grouped_function_tags['Show']) > 1:
            print("Multiple shows defined.")
            print()
            for i, tag in enumerate(grouped_function_tags['Show']):
                print(f"{i} - {tag.get('Name')}")
            print()
            show_selection = input("Please select one>")
        else:
            show_selection = 0

        show_functions = self._parse_show_functions(
            grouped_function_tags,
            show_selection
        )
        self._sequences = self._parse_sequences(
            grouped_function_tags,
            show_functions
        )

    def _serialize(self):
        self._serialized_data = {
            key: value
            for sequence in self._sequences.values()
            for key, value in sequence.serialize_data(self._fixtures).items()
        }

    def _compress(self):
        self._compressed_serialized_data = {}

        last_frame = {}
        for t, frame in self._serialized_data.items():
            compressed_frame = {}
            for channel, value in frame.items():
                if last_frame.get(channel) != value:
                    compressed_frame[channel] = value
            if len(compressed_frame) > 0:
                self._compressed_serialized_data[t] = compressed_frame
            last_frame = frame


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Wrong number of arguments.")
        exit(1)

    input_filename = sys.argv[1]

    if len(sys.argv) == 2:
        output_filename = f"{input_filename}.json"
    else:
        output_filename = sys.argv[2]

    converter = QxwConverter(input_filename, output_filename)
    converter.convert()

""" This module contains the methods for the ``openxc-dashboard`` command line
program.

`main` is executed when ``openxc-dashboard`` is run, and all other callables in
this module are internal only.
"""
from __future__ import absolute_import

import argparse
import curses
from datetime import datetime

from .common import device_options, configure_logging, select_device
from openxc.vehicle import Vehicle
from openxc.measurements import EventedMeasurement, Measurement

try:
    unicode
except NameError:
    # Python 3
    basestring = unicode = str


# timedelta.total_seconds() is only in 2.7, so we backport it here for 2.6
def total_seconds(delta):
    return (delta.microseconds + (delta.seconds
        + delta.days * 24 * 3600) * 10**6) / 10**6


# Thanks, SO: http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
def sizeof_fmt(num):
    for unit in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return "%3.1f%s" % (num, unit)
        num /= 1024.0


class DataPoint(object):
    def __init__(self, measurement_type):
        self.event = ''
        self.current_data = None
        self.events = {}
        self.messages_received = 0
        self.measurement_type = measurement_type

    def update(self, measurement):
        self.messages_received += 1
        self.current_data = measurement
        if isinstance(measurement, EventedMeasurement):
            if measurement.valid_state():
                self.events[measurement.value] = measurement.event

    def print_to_window(self, window, row, started_time):
        width = window.getmaxyx()[1]
        window.addstr(row, 0, self.current_data.name)
        if self.current_data is not None:
            if hasattr(self.measurement_type, 'valid_range'):
                # TODO leaking the unit class member here
                percent = ((self.current_data.value.num -
                    self.measurement_type.valid_range.min) /
                        float(self.measurement_type.valid_range.spread)) * 100
                chunks = int((percent - .1) * .1)
                graph = "*%s|%s*" % ("-" * chunks, "-" * (10 - chunks))
                window.addstr(row, 30, graph)

            if len(self.events) == 0:
                value = str(self.current_data)
            else:
                result = ""
                for item, value in enumerate(self.measurement_type.states):
                    # TODO missing keys here?
                    result += "%s: %s " % (value, self.events.get(item, "?"))
                value = result

            value_color = curses.color_pair(0)
            window.addstr(row, 45, value, value_color)

        if self.messages_received > 0:
            message_count_color = curses.color_pair(0)
        else:
            message_count_color = curses.color_pair(3)

        if width > 90:
            window.addstr(row, 80, "Messages: " + str(self.messages_received),
                    message_count_color)

        if width >= 115:
            window.addstr(row, 100, "Freq. (Hz): %d" %
                    (self.messages_received /
                        (total_seconds(datetime.now() - started_time) + 0.1)))


class Dashboard(object):
    def __init__(self, window, vehicle):
        self.window = window
        self.elements = {}
        vehicle.listen(Measurement, self.receive)

        self.started_time = datetime.now()
        self.messages_received = 0

        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)

    def receive(self, measurement, data_remaining=False, **kwargs):
        if self.messages_received == 0:
            self.started_time = datetime.now()
        self.messages_received += 1


        if measurement.name not in self.elements:
            self.elements[measurement.name] = DataPoint(measurement.__class__)
        self.elements[measurement.name].update(measurement)
        if not data_remaining:
            self._redraw()


    def _redraw(self):
        self.window.erase()
        max_rows = self.window.getmaxyx()[0] - 4
        for row, element in enumerate(sorted(self.elements.values(),
                key=lambda elt: elt.current_data.name)):
            if row > max_rows:
                break
            element.print_to_window(self.window, row, self.started_time)
        self.window.addstr(max_rows + 1, 0,
                "Message count: %d (%d corrupted)" % (self.messages_received,
                    self.source.corrupted_messages), curses.A_REVERSE)
        self.window.addstr(max_rows + 2, 0,
                "Total received: %s" %
                sizeof_fmt(self.source.bytes_received),
                curses.A_REVERSE)
        self.window.addstr(max_rows + 3, 0, "Data Rate: %s" %
            sizeof_fmt(self.source.bytes_received /
                (total_seconds(datetime.now() - self.started_time)
                    + 0.1)),
             curses.A_REVERSE)
        self.window.refresh()


def run_dashboard(window, source_class, source_kwargs):
    vehicle = Vehicle()
    dashboard = Dashboard(window, vehicle)
    dashboard.source = source_class(**source_kwargs)
    vehicle.add_source(dashboard.source)

    while True:
        import time
        time.sleep(5)


def parse_options():
    parser = argparse.ArgumentParser(
            description="View a real-time dashboard of all OpenXC measurements",
            parents=[device_options()])
    arguments = parser.parse_args()
    return arguments


def main():
    configure_logging()
    arguments = parse_options()
    source_class, source_kwargs = select_device(arguments)
    curses.wrapper(run_dashboard, source_class, source_kwargs)

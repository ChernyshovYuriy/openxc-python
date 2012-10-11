from nose.tools import eq_, ok_
import unittest

from openxc.sources.base import DataSource
from openxc.measurements import Measurement, UnrecognizedMeasurementError
from openxc.vehicle import Vehicle

class VehicleTests(unittest.TestCase):
    def setUp(self):
        super(VehicleTests, self).setUp()
        self.vehicle = Vehicle()

    def test_get(self):
        measurement = self.vehicle.get(TestMeasurement)
        ok_(measurement is None)

    def test_add_listener(self):
        def listener():
            pass

        self.vehicle.listen(Measurement, listener)


    def test_get_one(self):
        source = TestDataSource()
        self.vehicle.add_source(source)
        measurement = self.vehicle.get(TestMeasurement)
        ok_(measurement is None)

        data = {'name': TestMeasurement.NAME, 'value': 100}
        source.inject(data)
        measurement = self.vehicle.get(TestMeasurement)
        ok_(measurement is not None)
        eq_(measurement.NAME, data['name'])
        eq_(measurement.value, data['value'])

    def test_bad_measurement_type(self):
        try:
            self.vehicle.get(Measurement)
        except UnrecognizedMeasurementError:
            pass
        else:
            self.fail()


class TestMeasurement(Measurement):
    NAME = "test"


class TestDataSource(DataSource):
    def inject(self, message):
        self.callback(message)

    def run(self):
        pass

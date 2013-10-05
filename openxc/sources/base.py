"""Abstract base interface for vehicle data sources."""
import threading
import logging
import google.protobuf.message
from google.protobuf.internal.decoder import _DecodeVarint

from openxc import openxc_pb2
from openxc.formats.json import JsonFormatter

LOG = logging.getLogger(__name__)


class DataSource(threading.Thread):
    """Interface for all vehicle data sources. This inherits from Thread and
    when a source is added to a vehicle it attempts to call the ``start()``
    method if it exists. If an implementer of DataSource needs some background
    process to read data, it's just a matter of defining a ``run()`` method.

    A data source requires a callback method to be specified. Whenever new data
    is received, it will pass it to that callback.
    """
    def __init__(self, callback=None):
        """Construct a new DataSource.

        By default, DataSource threads are marked as ``daemon`` threads, so they
        will die as soon as all other non-daemon threads in the process have
        quit.

        Kwargs:
            callback - function to call with any new data received
        """
        super(DataSource, self).__init__()
        self.callback = callback
        self.daemon = True

    def _read(self, timeout=None):
        """Read data from the source.

        Kwargs:
            timeout (float) - if the source implementation could potentially
                block, timeout after this number of seconds.
        """
        raise NotImplementedError("Don't use DataSource directly")


class BytestreamDataSource(DataSource):
    """A source that receives data is a series of bytes, with discrete messages
    separated by a newline character.

    Subclasses of this class need only to implement the ``_read`` method.
    """

    def __init__(self, callback=None):
        super(BytestreamDataSource, self).__init__(callback)
        self.bytes_received = 0
        self.corrupted_messages = 0

    def run(self):
        """Continuously read data from the source and attempt to parse a valid
        message from the buffer of bytes. When a message is parsed, passes it
        off to the callback if one is set.
        """
        message_buffer = b""
        while True:
            try:
                message_buffer += self._read()
            except DataSourceError as e:
                LOG.warn("Can't read from data source -- stopping: %s", e)
                break

            while True:
                message, message_buffer, byte_count = self._parse_message(
                        message_buffer)
                if message is None:
                    break
                if not hasattr(message, '__iter__') or not (
                        ('name' in message and 'value' in message) or (
                        'id' in message and 'data' in message)):
                    self.corrupted_messages += 1
                    break

                self.bytes_received += byte_count
                if self.callback is not None:
                    self.callback(message,
                            data_remaining=len(message_buffer) > 0)

    def _parse_message(self, message_buffer):
        """If a message can be parsed from the given buffer, return it and
        remove it.

        Returns the message if one could be parsed, otherwise None, and the
        remainder of the buffer.
        """
        if not isinstance(message_buffer, bytes):
            message_buffer = message_buffer.encode("utf-8")
        parsed_message = None
        remainder = message_buffer
        message_data = ""
        footer_index = message_buffer.find(b"\0")
        if footer_index > -1 and footer_index + 1 < len(message_buffer):
            message_length, message_start = _DecodeVarint(message_buffer,
                    footer_index + 1)
            message_data = message_buffer[message_start:message_start + message_length]
            # TODO if we don't put the footer in the remainder, we miss the next
            # message...not sure if the consequences of that
            remainder = message_buffer[message_start + message_length:]
            if len(message_data) > 1:
                message = openxc_pb2.VehicleMessage()
                try:
                    message.ParseFromString(message_data)
                except google.protobuf.message.DecodeError as e:
                    LOG.warn("Unable to parse protobuf: %s", e)
                except UnicodeDecodeError as e:
                    LOG.warn("Unable to parse protobuf: %s", e)
                else:
                    parsed_message = {}
                    if message.type == message.RAW:
                        if message.raw_message.HasField('bus'):
                            parsed_message['bus'] = message.raw_message.bus
                        if message.raw_message.HasField('message_id'):
                            parsed_message['id'] = message.raw_message.message_id
                        if message.raw_message.HasField('data'):
                            parsed_message['data'] = "0x%x" % message.raw_message.data
                    else:
                        parsed_message['name'] = message.translated_message.name
                        if message.translated_message.HasField('numerical_value'):
                            parsed_message['value'] = message.translated_message.numerical_value
                        elif message.translated_message.HasField('boolean_value'):
                            parsed_message['value'] = message.translated_message.boolean_value
                        elif message.translated_message.HasField('string_value'):
                            parsed_message['value'] = message.translated_message.string_value

                        if message.translated_message.HasField('numerical_event'):
                            parsed_message['event'] = message.translated_message.numerical_event
                        elif message.translated_message.HasField('boolean_event'):
                            parsed_message['event'] = message.translated_message.boolean_event
                        elif message.translated_message.HasField('string_event'):
                            parsed_message['event'] = message.translated_message.string_event
        return parsed_message, remainder, len(message_data)

class DataSourceError(Exception):
    pass

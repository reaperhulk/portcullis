"""Prototype crypto proxy module, that demonstrates accepting a POST of chunked data
from a client to a Tornado server (via ChunkedHandler), which uses a state machine
(in ChunkFromClientStateMachine) to manage the receipt of the chunked data. Each input
chunk is encrypted (via SampleCryptoProcessor's encrypt_block() method) and then stored
in a buffer (managed via BufferManager). Another state machine (ChunkToTargetStateMachine)
manages sending/chunking the data to the target server, and draining the contents of
the buffer.

The input chunk size, the internal crypto block size (16 bytes by default), and the
output chunk sizes (4k by default) are all isolated and managed independently of
each other.

Caveats:
- No attempt to handle http errors!
- No attempt to throttle the in and out flows, so the buffer could become arbitrarily large!
- Only POSTs from a client are supported, though several of the classes should be reusable
  for either GETs or POSTs.
- When GETs are supported, the SampleCryptoProcessor could be used as is, but would be
  more secure to keep the inbound (from target server) encrypted data in the buffer, and only
  decrypted when data is pulled out via the 'read_xxxx()' methods.
"""

from tornado import (
    httpserver,
    httpclient,
    ioloop,
    iostream,
    options,
    web,
    curl_httpclient
)
from tornado.options import options as options_data
import socket


#TODO(jwood) Consider adding a base Processor class, that this one extends?
class SampleCryptoProcessor(object):
    def __init__(self, is_encrypt, block_size_bytes=16):
        self.block_size_bytes = block_size_bytes
        self.buffer = str()
        self.block_method = self._encrypt_block if is_encrypt else self._decrypt_block

    def process_data(self, data):
        """Accept and process the input 'data' block by applying the 'block_method()'
        to it. Return an 'output' that is a modulo of this processor's block size, which
        may not be evenly aligned with the input data's size.
        """
        if not data:
            return None

        output = str()
        self.buffer = ''.join([self.buffer, data])
        while len(self.buffer) >= self.block_size_bytes:  #TODO(jwood) How reliable is 'len()' over random binary bytes?
            output = ''.join([output,
                     self.block_method(self.buffer[:self.block_size_bytes])])
            self.buffer = self.buffer[self.block_size_bytes:]
        return output

    def finish(self):
        """Indicate that we are finished using this data structure, so need to output based on existing buffer data."""
        #TODO(jwood) Deal with non-modulo block sizes.
        output = self.block_method(self.buffer)
        self.buffer = str()
        return output

    def _encrypt_block(self, block):
        return block.upper()

    def _decrypt_block(self, block):
        return block.lower()


class BufferManager(object):
    def __init__(self, processor=None, max_buffer=4096):
        self.max_buffer = max_buffer
        self.processor = processor
        self.buffer = str()

    def receive_data(self, data):
        """Accept, process and store data in buffer."""
        #TODO(jwood) Yeah, probably not the most efficient queue structure.
        if self.processor:
            data = self.processor.process_data(data)
        if data:
            self.buffer = ''.join([self.buffer, data])

    def read_next_block(self):
        """Retrieve another 'max_buffer'-sized block of data from this buffer."""
        next_block = str()
        print(">>>> Buffer before next read: '{0}'".format(self.buffer))
        if len(self.buffer) >= self.max_buffer:
            next_block = self.buffer[:self.max_buffer]
            self.buffer = self.buffer[self.max_buffer:]
        print(">>>> Buffer next block: '{0}'".format(next_block))
        return next_block

    def read_all(self):
        """Force process and retrieve all remaining data from buffer."""
        if self.processor:
            data = self.processor.finish()
        if data:
            self.buffer = ''.join([self.buffer, data])

        last_block = self.buffer
        self.buffer = str()
        print(">>>> Buffer last block: '{0}'".format(last_block))
        return last_block


class ChunkToTargetStateMachine(object):
    """Handle chunking POST data to a target server (Swift for example)."""
    def __init__(self, callback_on_error):
        self.callback_on_error = callback_on_error

        #TODO(jwood) Get host/port info from http request itself, if using http proxy conventions
        #   that specify the entire target URL?
        self.host = b'localhost'
        self.port = 8080
        self.url = b"{0}:{1}".format(self.host, self.port)
        self.path = b'/chunked'

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.stream = iostream.IOStream(s)
        self.stream.connect((self.host, self.port), self._state_stream_is_idle)

        self.buffer_mgr = BufferManager(processor=SampleCryptoProcessor(is_encrypt=True))
        self.stream_is_ready = False
        self.stream_is_sent_first_chunk = False
        self.finish_is_needed = False

    def send_chunk_data(self, data):
        """Receive input chunk of 'data' to process and (eventually) send to target."""
        if data:
            self.buffer_mgr.receive_data(data)
        if self.stream_is_ready:
            self._state_stream_is_idle()

    def finish(self):
        """Indicate that we need to finish up processing."""
        self.finish_is_needed = True
        if self.stream_is_ready:
            self._state_stream_is_idle()

    def _state_stream_is_idle(self):
        """Indicate that we are entering an idle no-streaming-in-progress state."""
        self.stream_is_ready = True

        chunk = self.buffer_mgr.read_next_block()
        if not chunk and self.finish_is_needed:
            chunk = self.buffer_mgr.read_all()
        self._state_stream_is_busy(chunk)

    def _state_stream_is_busy(self, chunk):
        """Indicate that we are entering a need-to-stream-data state."""
        assert self.stream_is_ready
        self.stream_is_ready = False

        # Send the first chunk...make sure the http header is correct.
        if not self.stream_is_sent_first_chunk:
            self.stream_is_sent_first_chunk = True
            # Output HTTP POST header.
            #TODO(jwood): Yeah, just dealing with text chunking now...need to look at binary xfers next...
            header_out = (b"POST " + self.path + b" HTTP/1.1\r\nHost: " + self.url + b"\r\n" +
                 b"Content-Type: application/octet-stream\r\n" +
                 b"Transfer-Encoding: chunked\r\n" +
                 b"Expect: 100-continue\r\n" +
                 b"\r\n")
            if chunk:
                chunk_out = b'{0}\r\n{1}\r\n'.format(hex(len(chunk))[2:], chunk)
                self.stream.write(b'{0}{1}'.format(header_out, chunk_out),
                                  callback=self._state_stream_is_idle)
            else:
                self.stream.write(header_out,
                                  callback=self._state_stream_is_idle)

            #TODO(jwood) Handle this response from target server, trap on errors for example.
            self.stream.read_until_close(self._handle_read_closed)

        # Else POST the next chunk to the target server.
        elif chunk:
            self.stream.write(b'{0}\r\n{1}\r\n'.format(hex(len(chunk))[2:], chunk),
                              callback=self._state_stream_is_idle)

        # Else, we've sent all the data and the 'finish' state is called for, so
        #   output the closing 0-length chunk to end the long-running post.
        elif self.finish_is_needed:
            self.stream.write(b'0\r\n\r\n',
                              callback=self._state_finished)
        else:
            self.stream_is_ready = True

    def _handle_read_closed(self, response):
        #TODO(jwood) Handle error response from target server!
        print("Target response: {0}".format(response))

    def _state_finished(self):
        print("!!!! Finished sending to target")


#TODO(jwood): Could maybe add thread sleeps in here if the to-target state machine gets behind (so if
#  the buffer size gets too big).
class ChunkFromClientStateMachine(object):
    """Handle receiving chunked data POST-ed to our proxy server."""
    def __init__(self, stream, callback_on_done, callback_on_error):
        self.stream = stream
        self.callback_on_done = callback_on_done
        self.callback_on_error = callback_on_error

        self.machine_to_target = ChunkToTargetStateMachine(callback_on_error)

        # Start request process state machine.
        self._state_enter_look_for_length()

    def _state_enter_look_for_length(self):
        """Look for the chunk's length, calling back to _state_xxxx() when found."""
        self.stream.read_until(b'\r\n', self._state_callback_look_for_length)

    def _state_enter_process_data(self, chunk_length):
        """Pull in the chunk's data, calling back to _state_xxxx() when done."""
        self.stream.read_bytes(chunk_length + 2, self._state_callback_process_data)

    def _state_enter_done(self):
        self.machine_to_target.finish()
        self.callback_on_done()

    def _state_callback_look_for_length(self, data):
        """We now have length of the (to follow) chunk of data, setup to read it in."""
        print('state-callback:look_for_length(): {0}'.format(data))

        assert data[-2:] == b'\r\n', "chunk size ends with CRLF"
        chunk_length = int(data[:-2], 16)  # Size is always expressed in hex (0x##), so convert to base-10.
        print('...length={0}'.format(chunk_length))

        if chunk_length:
            self._state_enter_process_data(chunk_length)

        # A zero chunk lenght indicates we are done processing requests.
        else:
            self._state_enter_done()

    def _state_callback_process_data(self, data):
        """Process the chunk of data we just recieved."""
        print('state-callback:process_data()..."{0}"'.format(data))

        assert data[-2:] == b'\r\n', "chunk data ends with CRLF"
        # self.data.chunk.write(data[:-2])
        print('...writing:"{0}"'.format(data[:-2]))

        # Give next set of data to the to-target state machine to manage.
        self.machine_to_target.send_chunk_data(data[:-2])

        # Setup to process the next chunk of data.
        self._state_enter_look_for_length()


class ChunkedHandler(web.RequestHandler):
    """The proxy HTTP server's request instance, one created per client request."""
    @web.asynchronous
    def post(self):
        """Receive a POST request from a client."""
        print ("instance of handler:{0}".format(self))

        # we assume that the wrapping server has not sent/flushed the
        # 100 (Continue) response
        print('_handle_chunked()...{0}'.format(self.request.headers))
        if self.request.headers.get(b'Expect', None) == b'100-continue' and \
            not 'Content-Length' in self.request.headers and \
            self.request.headers.get(b'Transfer-Encoding', None) == b'chunked':

            print('...got chunked...')

            self._auto_finish = False
            ChunkFromClientStateMachine(self.request.connection.stream,
                                        self._callback_on_done,
                                        self._callback_on_error)

            self.request.write(b"HTTP/1.1 100 (Continue)\r\n\r\n")
        else:
            raise web.HTTPError(500, "non-chunked request")

    #TODO(jwood) Add GET method, and a chunk-to-client state machine and
    #  a chunk-from-target state machine.

    def _callback_on_done(self):
        """Indicates that we are done processing this request."""
        print('finish()')
        self.finish()

    def _callback_on_error(self, error):
        """Handle errors gracefully here."""
        print('error!()')
        self.set_status(500)
        # TODO(jwood) Causes write after finish exception: self.write('Internal server error:\n' + str(error))
        # self.finish()


if __name__ == '__main__':
    options.define("port", default=8000, help="run on the given port", type=int)
    options.parse_command_line()

    application = web.Application([
        ('/chunked$', ChunkedHandler, ),
    ])
    http_server = httpserver.HTTPServer(application)
    http_server.listen(options_data.port)
    print('Starting up server...')
    ioloop.IOLoop.instance().start()

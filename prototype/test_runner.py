#!/usr/bin/env python
#
# Downloads a large file in chunked encoding with both curl and simple clients

import logging
import socket
from tornado.curl_httpclient import CurlAsyncHTTPClient
from tornado.simple_httpclient import SimpleAsyncHTTPClient
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import RequestHandler, Application
import tornado.iostream


define('port', default=8000)
define('num_chunks', default=1000)
define('chunk_size', default=2048)

class ChunkHandler(RequestHandler):
    def get(self):
        for i in xrange(options.num_chunks):
            self.write('A' * options.chunk_size)
            self.flush()
        self.finish()


def main():
    host = b'localhost'
    port = options.port
    url = b"{0}:{1}".format(host, port)
    path = b'/chunked'
    url_base = b'http://localhost:%d/chunked' % options.port

    # Send a test chunking POST to a server.
    def send_request():
        stream.write(b"POST " + path + b" HTTP/1.1\r\nHost: " + url + b"\r\n" +
                     b"Content-Type: text/plain\r\n" +
                     b"Transfer-Encoding: chunked\r\n" +
                     b"Expect: 100-continue\r\n\r\n" +
                     b"1a\r\nabcdefghijklmnopqrstuvwxyz\r\n" +
                     b"10\r\n1234567890abcdef\r\n" +
                     b"0\r\n\r\n")
        stream.read_until_close(on_done)

    # def on_headers(data):
    #     print("Response: {0}".format(data))
    #     headers = {}
    #     for line in data.split(b"\r\n"):
    #        parts = line.split(b":")
    #        if len(parts) == 2:
    #            headers[parts[0].strip()] = parts[1].strip()
    #     stream.read_bytes(int(headers[b"Content-Length"]), on_body)

    def on_done(data):
        print("Data received: '{0}'".format(data))
        stream.close()
        tornado.ioloop.IOLoop.instance().stop()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    stream = tornado.iostream.IOStream(s)
    stream.connect((host, port), send_request)
    tornado.ioloop.IOLoop.instance().start()


def main_curl():
    # parse_command_line()
    # app = Application([('/', ChunkHandler)])
    # app.listen(options.port, address='127.0.0.1')
    def callback(response):
        # response.rethrow()
        # assert len(response.body) == (options.num_chunks * options.chunk_size)
        logging.warning("fetch completed in %s seconds", response.request_time)
        logging.warning("response status: %s", response.code)
        IOLoop.instance().stop()

    url = 'http://localhost:%d/chunked' % options.port
    logging.warning("Starting fetch with curl client from %s", url)
    curl_client = CurlAsyncHTTPClient()
    curl_client.fetch(request=url,
                      method='POST',
                      callback=callback,
                      body='testdatatestdata',
                      headers={'Transfer-Encoding': 'chunked',
                               'Expect': '100-continue'})
    IOLoop.instance().start()

    # logging.warning("Starting fetch with simple client")
    # simple_client = SimpleAsyncHTTPClient()
    # simple_client.fetch('http://localhost:%d/' % options.port,
    #                     callback=callback)
    # IOLoop.instance().start()


def main_orig():
    parse_command_line()
    app = Application([('/', ChunkHandler)])
    app.listen(options.port, address='127.0.0.1')
    def callback(response):
        response.rethrow()
        assert len(response.body) == (options.num_chunks * options.chunk_size)
        logging.warning("fetch completed in %s seconds", response.request_time)
        IOLoop.instance().stop()

    logging.warning("Starting fetch with curl client")
    curl_client = CurlAsyncHTTPClient()
    curl_client.fetch('http://localhost:%d/' % options.port,
                      callback=callback)
    IOLoop.instance().start()

    logging.warning("Starting fetch with simple client")
    simple_client = SimpleAsyncHTTPClient()
    simple_client.fetch('http://localhost:%d/' % options.port,
                        callback=callback)
    IOLoop.instance().start()


if __name__ == '__main__':
    main()

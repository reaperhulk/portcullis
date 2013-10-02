import tornado
import tornado.web
import tornado.httpserver
import tornado.httpclient


class ForwardingRequestHandler (tornado.web.RequestHandler):
    def get(self):
        self.forward()

    def handle_response(self, response):
        if response.error and not isinstance(response.error, tornado.httpclient.HTTPError):
            self.set_status(500)
            self.write("Internal server error:\n" + str(response.error))
            self.finish()
        else:
            self.set_status(response.code)
            for header in ("Date", "Cache-Control", "Server", "Content- Type", "Location"):
                v = response.headers.get(header)
                if v:
                    self.set_header(header, v)
            if response.body:
                self.write(response.body)
            self.finish()

    def forward(self, port=None, host=None):
        try:
            tornado.httpclient.AsyncHTTPClient().fetch(
                tornado.httpclient.HTTPRequest(
                    #url="%s://%s:%s%s" % (
                    #    self.request.protocol, host or "127.0.0.1", port or 80, self.request.uri),
                    url = "http://www.google.com",
                    method=self.request.method,
                    body=self.request.body,
                    headers=self.request.headers,
                    follow_redirects=False),
                self.handle_response)
        except tornado.httpclient.HTTPError, x:
            if hasattr(x, response) and x.response:
                self.handle_response(x.response)
        except tornado.httpclient.CurlError, x:
            self.set_status(500)
            self.write("Internal server error:\n" + ''.join(traceback.format_exception(*sys.exc_info())))
            self.finish()
        except:
            self.set_status(500)
            self.write("Internal server error:\n" + ''.join(traceback.format_exception(*sys.exc_info())))
            self.finish()


if __name__ == '__main__':
    application = tornado.web.Application([
        ('/$', ForwardingRequestHandler, ),
    ])
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(8000)
    print('Starting up server...')
    tornado.ioloop.IOLoop.instance().start()

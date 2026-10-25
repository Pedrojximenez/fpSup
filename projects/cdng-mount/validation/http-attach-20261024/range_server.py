# Minimal HTTP/1.1 server with Range support (probe for hdiutil http attach).
import http.server, os, sys, re
PATH = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, fmt, *a): sys.stderr.write((fmt % a) + '\n')
    def _hdr(self, code, length, start=None, end=None, size=None):
        self.send_response(code)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(length))
        if start is not None: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
    def do_HEAD(self):
        self._hdr(200, os.path.getsize(PATH))
    def do_GET(self):
        size = os.path.getsize(PATH)
        m = re.match(r'bytes=(\d+)-(\d*)', self.headers.get('Range', ''))
        with open(PATH, 'rb') as f:
            if m:
                s = int(m.group(1)); e = int(m.group(2)) if m.group(2) else size - 1
                f.seek(s); data = f.read(e - s + 1)
                self._hdr(206, len(data), s, s + len(data) - 1, size)
            else:
                data = f.read(); self._hdr(200, len(data))
            self.wfile.write(data)
http.server.ThreadingHTTPServer(('127.0.0.1', int(sys.argv[2])), H).serve_forever()

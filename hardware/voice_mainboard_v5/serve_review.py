"""Loopback-only preview server with an explicit allowlist."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse
import argparse,mimetypes
ROOT=Path(__file__).resolve().parent
files={'/':ROOT/'exports/review.html','/front.svg':ROOT/'exports/front.svg','/back.svg':ROOT/'exports/back.svg',
    '/assembly.svg':ROOT/'exports/assembly.svg','/schematic.svg':ROOT/'exports/schematic/voice_mainboard_v5.svg',
    '/validation.json':ROOT/'exports/validation.json','/bom.json':ROOT/'cost/bom-budget.json',
    '/voice-v5-review.zip':ROOT/'exports/voice-v5-review.zip'}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        file=files.get(urlparse(self.path).path)
        if file is None or not file.is_file():self.send_error(404);return
        body=file.read_bytes();self.send_response(200)
        self.send_header('Content-Type',mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18897)
    args=parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()

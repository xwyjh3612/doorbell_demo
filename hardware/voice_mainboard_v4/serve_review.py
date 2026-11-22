"""Serve selected V4 engineering artifacts on loopback only."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse
import mimetypes,argparse
ROOT=Path(__file__).resolve().parent
files={'/':ROOT/'exports/review.html','/front.svg':ROOT/'exports/front.svg','/back.svg':ROOT/'exports/back.svg',
       '/schematic.svg':ROOT/'exports/schematic/voice_mainboard_v4.svg',
       '/validation.json':ROOT/'exports/validation.json','/bom.json':ROOT/'cost/bom-budget.json'}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        f=files.get(urlparse(self.path).path)
        if f is None or not f.is_file():self.send_error(404);return
        body=f.read_bytes();self.send_response(200)
        self.send_header('Content-Type',mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18896);a=parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()

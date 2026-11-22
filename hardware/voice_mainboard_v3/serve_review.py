"""Loopback-only review of selected public project artifacts."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
import mimetypes,argparse
root=Path(__file__).resolve().parent;repo=root.parent.parent
files={'/':root/'exports/review.html','/review.html':root/'exports/review.html',
 '/front.svg':root/'exports/front.svg','/back.svg':root/'exports/back.svg',
 '/schematic.svg':root/'exports/schematic/voice_mainboard_v3.svg',
 '/validation.json':root/'exports/validation.json',
 '/cost.xlsx':repo/'outputs/voice-v3-20261122/语音对讲V3主板费用.xlsx',
 '/project.zip':root/'exports/voice-v3-engineering-review.zip'}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=files.get(urlparse(self.path).path)
        if path is None or not path.is_file():self.send_error(404);return
        content=path.read_bytes();self.send_response(200)
        self.send_header('Content-Type',mimetypes.guess_type(str(path))[0]or'application/octet-stream')
        self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(content)
    def log_message(self,*args):pass
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18895);a=parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()

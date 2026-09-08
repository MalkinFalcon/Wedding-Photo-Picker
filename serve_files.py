"""Local stand-in for the R2 bucket: serves _out/ with CORS, and resolves /o/<oid>.<ext>
straight to the original files so nothing needs copying. Port 8791."""
import os, json, mimetypes
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

SITE    = os.path.dirname(os.path.abspath(__file__))
WEDDING = os.path.dirname(SITE)
OUT     = os.path.join(SITE, '_out')

def originals():
    ids = json.load(open(os.path.join(SITE, 'photo_ids.json'), encoding='utf-8'))
    man = {r['id']: r['src'] for r in json.load(open(os.path.join(WEDDING, '_peopleapp', 'manifest.json'), encoding='utf-8'))}
    return {oid: os.path.join(WEDDING, man[pid].replace('/', os.sep)) for pid, oid in ids.items() if pid in man}

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=OUT, **k)
    def log_message(self, *a): pass
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
    def translate_path(self, path):
        p = unquote(path.split('?', 1)[0])
        if p.startswith('/o/'):
            oid = os.path.splitext(os.path.basename(p))[0]
            src = ORIG.get(oid)
            if src: return src
        return super().translate_path(path)
    def guess_type(self, path):
        return mimetypes.guess_type(path)[0] or 'application/octet-stream'

if __name__ == '__main__':
    ORIG = originals() if os.path.isfile(os.path.join(SITE, 'photo_ids.json')) else {}
    os.makedirs(OUT, exist_ok=True)
    print(f'files: http://localhost:8791  ({len(ORIG)} originals mapped)', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8791), H).serve_forever()

"""Build susieanddima.com from the picker app's state.

Inputs
  ../_peopleapp/state.json      scope / assign / show / people   (the picker app)
  ../_peopleapp/manifest.json   photo id -> source path
  guests.csv                    app_name, display_name, url_key, photos
  .r2.env                       ACCOUNT_ID / ACCESS_KEY / SECRET_KEY / BUCKET / PUBLIC_URL  (optional)

Outputs
  docs/                showcase images + showcase.json + config.json   (GitHub Pages, public)
  _out/                everything guest-specific, mirrored to R2        (git-ignored)
     o/<oid>.<ext>     originals are NOT copied here - uploaded straight from source
     p/<oid>.jpg       1600px preview          t/<oid>.jpg  400px thumb
     g/<key>.json      guest manifest          g/<key>.zip  all originals (if under ZIP_MAX_MB)
  photo_ids.json       stable random id per photo (git-ignored; keep it, or every URL changes)

Usage
  python build.py                build + upload (upload skipped if .r2.env is missing)
  python build.py --no-upload    build only
  python build.py --push         also commit docs/ and push to GitHub
"""
import os, sys, json, csv, random, zipfile, argparse, mimetypes
import pillow_heif; pillow_heif.register_heif_opener()
from PIL import Image, ImageOps, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

SITE    = os.path.dirname(os.path.abspath(__file__))
WEDDING = os.path.dirname(SITE)
APP     = os.path.join(WEDDING, '_peopleapp')
DOCS    = os.path.join(SITE, 'docs')
OUT     = os.path.join(SITE, '_out')
GUESTS  = os.path.join(SITE, 'guests.csv')
IDS     = os.path.join(SITE, 'photo_ids.json')
ENV     = os.path.join(SITE, '.r2.env')

ZIP_MAX_MB   = 250                    # bigger bundles get per-photo / selected downloads only
SHOWCASE_PX  = 1600
PREVIEW_PX   = 1600
THUMB_PX     = 480
ALPHABET     = 'abcdefghjkmnpqrstuvwxyz23456789'   # no i l o 0 1 - these get read aloud / typed
DL_PREFIX    = 'SusieAndDima'
ORIGINS      = ['https://susieanddima.com', 'https://www.susieanddima.com',
                'http://localhost:8790', 'http://127.0.0.1:8790']

def log(*a): print(*a, flush=True)
def rand(n): return ''.join(random.SystemRandom().choice(ALPHABET) for _ in range(n))
def mb(b): return f'{b / 1e6:.0f} MB'

def load_json(p, default):
    try:
        with open(p, encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError:
        return default

def save_json(p, obj, **kw):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f: json.dump(obj, f, **kw)
    os.replace(tmp, p)

def load_env():
    if not os.path.isfile(ENV): return None
    env = {}
    for line in open(ENV, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1); env[k.strip()] = v.strip().strip('"').strip("'")
    need = ['ACCOUNT_ID', 'ACCESS_KEY', 'SECRET_KEY']
    missing = [k for k in need if not env.get(k)]
    if missing:
        log(f'!! .r2.env is missing {missing} - skipping upload'); return None
    env.setdefault('BUCKET', 'wedding-photos')
    if not env.get('PUBLIC_URL'):
        log('!! .r2.env has no PUBLIC_URL (the https://pub-xxxx.r2.dev address) - skipping upload'); return None
    env['PUBLIC_URL'] = env['PUBLIC_URL'].rstrip('/')
    return env

def web_image(src, dst, px, q):
    """Resize src to fit px, save jpeg at dst; returns (w, h). Cached on disk."""
    if os.path.isfile(dst):
        with Image.open(dst) as im: return im.size
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((px, px), Image.LANCZOS)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im.convert('RGB').save(dst, 'JPEG', quality=q, optimize=True, progressive=True)
        return im.size

# ----------------------------------------------------------------------------- guests.csv
def read_guests():
    rows = []
    with open(GUESTS, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            r = {k.strip(): (v or '').strip() for k, v in r.items()}
            if r.get('app_name'): rows.append(r)
    return rows

def write_guests(rows, counts):
    with open(GUESTS, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['app_name', 'display_name', 'url_key', 'photos'])
        for r in rows:
            w.writerow([r['app_name'], r['display_name'], r['url_key'], counts.get(r['app_name'], 0)])

# ----------------------------------------------------------------------------- build
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-upload', action='store_true')
    ap.add_argument('--push', action='store_true')
    args = ap.parse_args()

    state    = load_json(os.path.join(APP, 'state.json'), {})
    manifest = {r['id']: r['src'] for r in load_json(os.path.join(APP, 'manifest.json'), [])}
    assign   = {k: v for k, v in state.get('assign', {}).items() if k in manifest and v}
    show     = [k for k in sorted(state.get('show', {})) if k in manifest]
    src_of   = lambda pid: os.path.join(WEDDING, manifest[pid].replace('/', os.sep))

    # --- guests: fill blank keys, warn about mismatches -------------------------------
    guests = read_guests()
    counts = {}
    for pid, names in assign.items():
        for n in names: counts[n] = counts.get(n, 0) + 1
    known = set(state.get('people', []))
    used = {r['url_key'] for r in guests if r['url_key']}
    for r in guests:
        if not r['display_name']: r['display_name'] = r['app_name']
        if not r['url_key']:
            while (k := rand(8)) in used: pass
            r['url_key'] = k; used.add(k)
        if r['app_name'] not in known:
            log(f"!! guests.csv row '{r['app_name']}' is not a person in the app - it will get no photos")
    for n in sorted(known - {r['app_name'] for r in guests}):
        log(f"!! app person '{n}' ({counts.get(n, 0)} photos) is not in guests.csv - add a row to publish them")
    write_guests(guests, counts)

    # --- stable random id per photo ------------------------------------------------------
    ids = load_json(IDS, {})
    for pid in assign:
        if pid not in ids:
            while (o := rand(10)) in ids.values(): pass
            ids[pid] = o
    save_json(IDS, ids, indent=1)

    # --- showcase -> docs/img/s ------------------------------------------------------------
    sdir = os.path.join(DOCS, 'img', 's')
    if show:
        os.makedirs(sdir, exist_ok=True)
        keep, items = set(), []
        for i, pid in enumerate(show, 1):
            f = f'{i:02d}.jpg'; keep.add(f)
            # regenerate if the slot now holds a different photo
            meta = os.path.join(sdir, f + '.src')
            if not (os.path.isfile(meta) and open(meta).read() == pid):
                try: os.remove(os.path.join(sdir, f))
                except FileNotFoundError: pass
                open(meta, 'w').write(pid)
            w, h = web_image(src_of(pid), os.path.join(sdir, f), SHOWCASE_PX, 82)
            items.append({'f': 'img/s/' + f, 'w': w, 'h': h})
        for f in os.listdir(sdir):
            if f.endswith('.jpg') and f not in keep:
                os.remove(os.path.join(sdir, f)); os.remove(os.path.join(sdir, f + '.src'))
        save_json(os.path.join(DOCS, 'showcase.json'), items)
        log(f'showcase: {len(items)} photos')
    else:
        proto = load_json(os.path.join(DOCS, 'img', 'list.json'), [])
        save_json(os.path.join(DOCS, 'showcase.json'), [{'f': 'img/' + p['f'], 'w': p['w'], 'h': p['h']} for p in proto])
        log(f'showcase: nothing starred yet - using the {len(proto)} prototype photos (press W in the picker)')

    # --- per-photo web assets (deduped across guests) -------------------------------------
    info = {}
    for n, pid in enumerate(sorted(assign), 1):
        oid, src = ids[pid], src_of(pid)
        ext = os.path.splitext(src)[1].lower().lstrip('.')
        ext = 'jpg' if ext == 'jpeg' else ext
        w, h = web_image(src, os.path.join(OUT, 'p', oid + '.jpg'), PREVIEW_PX, 84)
        web_image(src, os.path.join(OUT, 't', oid + '.jpg'), THUMB_PX, 80)
        info[pid] = {'id': oid, 'ext': ext, 'w': w, 'h': h, 'bytes': os.path.getsize(src),
                     'name': f'{DL_PREFIX}_{pid[:-4]}.{ext}', 'src': src}
        if n % 50 == 0: log(f'  web assets {n}/{len(assign)}')
    log(f'photos: {len(info)} unique, {mb(sum(i["bytes"] for i in info.values()))} of originals')

    # --- guest manifests + zips ---------------------------------------------------------------
    gdir = os.path.join(OUT, 'g'); os.makedirs(gdir, exist_ok=True)
    zip_total = 0
    for r in guests:
        pids = sorted(pid for pid, names in assign.items() if r['app_name'] in names)
        if not pids: continue
        total = sum(info[p]['bytes'] for p in pids)
        zippable = total <= ZIP_MAX_MB * 1e6
        zpath = os.path.join(gdir, r['url_key'] + '.zip')
        if zippable:
            want = [info[p]['name'] for p in pids]
            stale = True
            if os.path.isfile(zpath):
                with zipfile.ZipFile(zpath) as z: stale = sorted(z.namelist()) != sorted(want)
            if stale:
                with zipfile.ZipFile(zpath + '.tmp', 'w', zipfile.ZIP_STORED) as z:
                    for p in pids: z.write(info[p]['src'], info[p]['name'])
                os.replace(zpath + '.tmp', zpath)
            zip_total += os.path.getsize(zpath)
        elif os.path.isfile(zpath):
            os.remove(zpath)
        save_json(os.path.join(gdir, r['url_key'] + '.json'), {
            'name': r['display_name'], 'count': len(pids), 'bytes': total, 'zip': zippable,
            'photos': [{k: info[p][k] for k in ('id', 'ext', 'w', 'h', 'bytes', 'name')} for p in pids],
        })
        log(f"  {r['display_name']:28} {len(pids):3} photos  {mb(total):>8}  {'zip' if zippable else 'no zip (too big)'}   #{r['url_key']}")
    log(f'zips: {mb(zip_total)}')

    # --- site config -----------------------------------------------------------------------------
    env = None if args.no_upload else load_env()
    # never let a localhost address reach the live site: without R2 the page shows "coming soon"
    files_url = env['PUBLIC_URL'] if env else ('' if args.push else 'http://localhost:8791')
    if args.push and not env: log('!! pushing without R2 configured - guest downloads will show "coming soon"')
    save_json(os.path.join(DOCS, 'config.json'), {'files': files_url})
    log(f'config.json -> files served from {files_url}')

    if env: upload(env, info, guests, gdir)
    if args.push: push()

# ----------------------------------------------------------------------------- R2
def upload(env, info, guests, gdir):
    import boto3
    from boto3.s3.transfer import TransferConfig
    s3 = boto3.client('s3', region_name='auto',
                      endpoint_url=f"https://{env['ACCOUNT_ID']}.r2.cloudflarestorage.com",
                      aws_access_key_id=env['ACCESS_KEY'], aws_secret_access_key=env['SECRET_KEY'])
    B = env['BUCKET']
    s3.put_bucket_cors(Bucket=B, CORSConfiguration={'CORSRules': [{
        'AllowedOrigins': ORIGINS, 'AllowedMethods': ['GET', 'HEAD'],
        'AllowedHeaders': ['*'], 'ExposeHeaders': ['Content-Length'], 'MaxAgeSeconds': 86400}]})

    existing = {}
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=B):
        for o in page.get('Contents', []): existing[o['Key']] = o['Size']

    jobs = []   # (key, path, extra, always)
    for i in info.values():
        ctype = mimetypes.guess_type('x.' + i['ext'])[0] or 'application/octet-stream'
        jobs.append((f"o/{i['id']}.{i['ext']}", i['src'],
                     {'ContentType': ctype, 'ContentDisposition': f'attachment; filename="{i["name"]}"',
                      'CacheControl': 'public, max-age=31536000'}, False))
        for kind in ('p', 't'):
            jobs.append((f"{kind}/{i['id']}.jpg", os.path.join(OUT, kind, i['id'] + '.jpg'),
                         {'ContentType': 'image/jpeg', 'CacheControl': 'public, max-age=31536000'}, False))
    for r in guests:
        j = os.path.join(gdir, r['url_key'] + '.json')
        if not os.path.isfile(j): continue
        jobs.append((f"g/{r['url_key']}.json", j,
                     {'ContentType': 'application/json', 'CacheControl': 'no-cache'}, True))
        z = os.path.join(gdir, r['url_key'] + '.zip')
        if os.path.isfile(z):
            safe = ''.join(c for c in r['display_name'] if c.isalnum() or c in ' -_').strip().replace(' ', '_')
            jobs.append((f"g/{r['url_key']}.zip", z,
                         {'ContentType': 'application/zip',
                          'ContentDisposition': f'attachment; filename="{DL_PREFIX}_{safe}.zip"',
                          'CacheControl': 'no-cache'}, False))

    todo = [j for j in jobs if j[3] or existing.get(j[0]) != os.path.getsize(j[1])]
    size = sum(os.path.getsize(j[1]) for j in todo)
    log(f'R2: {len(jobs)} objects, {len(todo)} to upload ({mb(size)}), {len(existing)} already there')
    cfg = TransferConfig(multipart_threshold=64 * 1024 * 1024, max_concurrency=4)
    done = 0
    for key, path, extra, _ in todo:
        s3.upload_file(path, B, key, ExtraArgs=extra, Config=cfg)
        done += os.path.getsize(path)
        if key.startswith('g/') or done and int(done / size * 20) != int((done - os.path.getsize(path)) / size * 20):
            log(f'  {mb(done)} / {mb(size)}   {key}')
    wanted = {j[0] for j in jobs}
    stray = [k for k in existing if k not in wanted]
    if stray: log(f'note: {len(stray)} objects in the bucket are no longer referenced (left in place)')
    log('R2: done')

def push():
    import subprocess
    run = lambda *a: subprocess.run(['git', '-C', SITE, *a], check=True)
    run('add', 'docs')
    if subprocess.run(['git', '-C', SITE, 'diff', '--cached', '--quiet']).returncode == 0:
        log('git: nothing to push'); return
    run('commit', '-q', '-m', 'Rebuild site from picker state')
    run('push', '-q', 'origin', 'main')
    log('git: pushed - GitHub Pages redeploys in about a minute')

if __name__ == '__main__':
    main()

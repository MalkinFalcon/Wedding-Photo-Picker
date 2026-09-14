# susieanddima.com — photo site

Public showcase (drifting polaroids on desktop, film reel on mobile) plus a private
per-guest page where each guest downloads their own photos at original quality.

- **Page**: GitHub Pages from `docs/` (this repo, custom domain `susieanddima.com`).
- **Files**: Cloudflare R2 bucket, public, unguessable paths. Nothing guest-specific lives in this repo.
- **Source of truth**: the picker app at `../_peopleapp` (`state.json`) + `guests.csv`.

## Morning checklist

1. **Star the showcase** — in the picker (`python ../_peopleapp/server.py`, http://localhost:8778)
   press `W` on ~20 photos. `★ Showcase` filter shows what you've picked.
2. **`guests.csv`** — edit `display_name` (what the greeting says). Leave `url_key` blank to
   have one generated, or type your own (letters/digits, lowercase).
3. **R2** — create bucket `wedding-photos`, allow public access, note the `https://pub-….r2.dev` URL,
   create an API token (Object Read & Write). Save as `.r2.env`:
   ```
   ACCOUNT_ID=…
   ACCESS_KEY=…
   SECRET_KEY=…
   BUCKET=wedding-photos
   PUBLIC_URL=https://pub-xxxxxxxx.r2.dev
   ```
4. **Build + upload + publish**:
   ```
   python build.py --push
   ```
   First run uploads ~4 GB (originals) + zips; later runs only upload what changed.
5. **Send links**: `https://susieanddima.com/#<url_key>` — keys are name slugs (`#arthur-and-naz`), listed in `guests.csv`.
   Guests can also type the name on the site if a link gets mangled.

## Bucket CORS (once, in the dashboard)

The API token is object-level, so the build cannot set this itself. Bucket → Settings → **CORS Policy → Add**, paste:

```json
[
  {
    "AllowedOrigins": ["https://susieanddima.com", "https://www.susieanddima.com"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["Content-Length"],
    "MaxAgeSeconds": 86400
  }
]
```
Without it, images and single downloads still work; only "Download selected" (browser-side zip) fails.

## Local preview (no R2 needed)

```
python build.py --no-upload
python serve_files.py            # files on :8791
python -m http.server 8790 --directory docs
```
Open http://localhost:8790/#<url_key>.

## Landing page rules

- Always the 10 pinned showcase photos, plus up to 10 of the guest's own, filled to 20 from the rest of the showcase.
- Desktop: polaroids drift; drag one to throw it. "See my photos" gathers them into the centre, then the gallery fades in.
- Mobile: film reel rolls; "See my photos" spins it up (~3.6 s, blur) then the gallery fades in. Confetti on first reveal.
- Guests tagged C / M / C&M in the picker also receive the China_All / Melbourne_All pools.

## How a guest's page works

`#<key>` → fetch `FILES/g/<key>.json` (name + photo list) → thumbs from `t/`, lightbox from `p/`,
originals from `o/` (served with `Content-Disposition: attachment`, so a tap downloads).
"Download all" uses the pre-built `g/<key>.zip` when the set is under 250 MB; otherwise the page
zips a selection in the browser (fflate). The key is remembered in the browser and removed from the
address bar after loading.

## Files that must never be committed

`.r2.env` (credentials), `guests.csv` (URL keys), `photo_ids.json` (the unguessable paths), `_out/`.
All are in `.gitignore`.

// Guestbook for susieanddima.com. Notes live in the same R2 bucket as the photos,
// one object per note under guestbook/. Posting requires a real guest key.
const ORIGINS = ['https://susieanddima.com', 'https://www.susieanddima.com', 'http://localhost:8790', 'http://127.0.0.1:8790'];

export default {
  async fetch(req, env) {
    const origin = req.headers.get('Origin') || '';
    const cors = {
      'Access-Control-Allow-Origin': ORIGINS.includes(origin) ? origin : ORIGINS[0],
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Cache-Control': 'no-store',
    };
    const json = (obj, status = 200) => new Response(JSON.stringify(obj), {status, headers: {...cors, 'Content-Type': 'application/json'}});
    if (req.method === 'OPTIONS') return new Response(null, {headers: cors});
    const url = new URL(req.url);
    if (url.pathname !== '/notes') return json({error: 'not found'}, 404);

    if (req.method === 'GET') {
      const list = await env.BUCKET.list({prefix: 'guestbook/', limit: 1000});
      const notes = await Promise.all(list.objects.map(async o => {
        const obj = await env.BUCKET.get(o.key);
        return obj ? obj.json() : null;
      }));
      return json(notes.filter(Boolean).sort((a, b) => b.ts - a.ts).map(({name, message, ts}) => ({name, message, ts})));
    }

    if (req.method === 'POST') {
      let body;
      try { body = await req.json(); } catch (e) { return json({error: 'bad json'}, 400); }
      const key = String(body.key || '').toLowerCase();
      const name = String(body.name || '').trim().slice(0, 60);
      const message = String(body.message || '').trim().slice(0, 600);
      if (!/^[a-z0-9-]{1,40}$/.test(key) || !message || !name) return json({error: 'missing fields'}, 400);
      if (!(await env.BUCKET.head(`g/${key}.json`))) return json({error: 'unknown guest'}, 403);
      const ts = Date.now();
      await env.BUCKET.put(`guestbook/${ts}-${key}.json`, JSON.stringify({key, name, message, ts}),
                           {httpMetadata: {contentType: 'application/json'}});
      return json({ok: true, ts}, 201);
    }
    return json({error: 'method'}, 405);
  },
};

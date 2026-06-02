# AI-butler Workers API validation

This is an isolated Cloudflare Workers migration spike. It does not replace the
current Render/FastAPI backend and the frontend does not point here by default.

## What this validates

- `/api/health`: Worker runtime and CORS are reachable.
- `/api/edge-check/auth`: Supabase access token can be verified from JWKS.
- `/api/profile/companion`: Worker can verify JWT, read Supabase REST with the
  service key, and return the same shape as the FastAPI endpoint.
- `/api/edge-check/llm`: optional DeepSeek ping to prove Worker can call an LLM.

## Required secrets

Set these in Cloudflare before deploying:

```bash
npx wrangler secret put SUPABASE_URL
npx wrangler secret put SUPABASE_SERVICE_KEY
npx wrangler secret put DEEPSEEK_API_KEY
```

`DEEPSEEK_API_KEY` is only needed for `/api/edge-check/llm`.

For local testing, create `workers-api/.dev.vars`:

```text
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
DEEPSEEK_API_KEY=optional-for-llm-ping
ALLOWED_ORIGINS=http://localhost:5173
```

Do not commit `.dev.vars`.

## Local checks

```bash
cd workers-api
npm install
npm run check
npm run dev
```

Then call:

```bash
curl http://localhost:8787/api/health
curl http://localhost:8787/api/edge-check/auth \
  -H "Authorization: Bearer <supabase_access_token>"
curl http://localhost:8787/api/profile/companion \
  -H "Authorization: Bearer <supabase_access_token>"
curl -X POST http://localhost:8787/api/edge-check/llm \
  -H "Authorization: Bearer <supabase_access_token>"
```

## Frontend trial

Only for local/preview validation:

```text
VITE_API_BASE_URL=http://localhost:8787
```

At this stage only `/api/profile/companion` is mirrored. Do not point the whole
frontend at this Worker as a production backend yet.

## Notes

- The Worker uses Web Crypto (`crypto.subtle`) to verify Supabase JWTs.
- Supabase REST is called from the Worker with the service key, matching the
  current FastAPI trust boundary.
- Waiting on network `fetch()` calls should not count as Worker CPU time, but
  `/api/chat` still needs a separate spike because prompt assembly and tool
  calling are much heavier than this validation slice.

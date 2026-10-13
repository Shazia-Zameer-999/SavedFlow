# SavedFlow

SavedFlow is a personal knowledge-management backend for turning Instagram
saved Reels/posts (programming tricks, dev tools, Flask, MongoDB, Git, AI,
etc.) into an actual learning-and-implementation system, instead of a pile
of links you never revisit.

This is the **V1 backend**. There is deliberately no styled frontend - just
a bare `templates/test.html` page for manually poking at the API. The
product for this phase is the API and the data model behind it.

---

## 1. What SavedFlow actually does

```
Instagram Saved Content
        |
Legitimate Import (manual URLs / data export / official API where supported)
        v
    MongoDB
        v
   AI Analysis (via Gemini)
        v
Extract Knowledge / Score Usefulness / Rank
        v
Recommend what to WATCH and what to IMPLEMENT
        v
Track your actions and results
        v
Personalized recommendations that improve over time
```

## 2. Important: what this project does NOT do (read this first)

- It does **not** scrape Instagram.
- It does **not** automate a browser to bypass Instagram's restrictions.
- It does **not** invent unsupported API endpoints (there is no `/me/saved`
  in Meta's public API, and this code does not pretend there is).
- It does **not** download or otherwise access Instagram video content
  without legitimate authorization.
- It does **not** fabricate AI analysis for content it was never given.

### The Instagram "Saved" API limitation

As of this project's implementation, **Meta's official Instagram Graph
API / Instagram API with Instagram Login does not expose a user's private
"Saved" collection** to third-party apps. There is no supported endpoint
for reading what a personal account has saved. This is a platform
limitation, not a missing feature in SavedFlow.

`POST /api/import/instagram` reflects this honestly:

```json
{
  "success": false,
  "available": false,
  "reason": "Instagram's official API does not expose the user's private Saved collection. ..."
}
```

The app still functions fully via the other two import methods below.
`services/instagram/api_importer.py` also implements one _legitimate_,
narrower use of the official API - fetching a connected business/creator
account's own **published** media (not Saved posts) via
`/{ig-user-id}/media` - which the API does genuinely support, in case
that's useful later.

If Meta ever adds official support for reading a user's Saved collection,
update `services/instagram/api_importer.py` after checking Meta's current
developer docs for the real endpoint and permissions - don't guess.

## 3. Architecture

```
savedflow/
├── app.py                     # Flask app factory + entrypoint
├── config.py                  # Env-var based configuration
├── extensions.py               # MongoDB connection + index creation
│
├── routes/                    # Thin HTTP layer - one blueprint per concern
│   ├── health.py
│   ├── items.py               # items CRUD + watch/apply tracking
│   ├── imports.py              # manual / export / official-API import
│   ├── ai.py                   # analyze / reanalyze / jobs
│   ├── actions.py
│   ├── recommendations.py
│   ├── dashboard.py
│   ├── preferences.py
│   └── reviews.py              # weekly review
│
├── services/
│   ├── instagram/               # BaseImporter + 3 concrete importers
│   ├── ai/                      # client, prompts, analyzer, ranking,
│   │                            # recommendations, duplicate_detector
│   ├── media/                   # video, frame, transcript, and GridFS evidence
│   └── jobs/                    # MongoDB-backed job creation and claiming
│
├── models/                     # plain-dict schema builders (no heavy ORM)
├── utils/                      # url validation, errors, pagination, dates
├── tests/                       # pytest + mongomock, no real credentials needed
└── templates/test.html          # unstyled manual-testing page
```

Each import method (`InstagramAPIImporter`, `InstagramExportImporter`,
`ManualURLImporter`) implements the same `BaseImporter.run()` contract, so
`routes/imports.py` treats them uniformly.

AI analysis never claims to have seen content it wasn't given
(`services/ai/analyzer.py::determine_available_content`) - every stored
analysis records its `analysis_basis` (`METADATA_ONLY`, `TRANSCRIPT`,
`AUDIO`, `VIDEO`, or `FRAMES`).

## 4. Requirements

- Python 3.10+
- MongoDB running locally (or a `MONGO_URI` pointing at one) - **not**
  required to run the test suite, which uses `mongomock`.
- A Gemini API key (optional - the app runs and reports itself as
  correctly "not configured" without one; AI analysis and AI analysis will report a configuration error until a key is set).

## 5. Setup

```bash
cd savedflow
python -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
# Create .env with your MongoDB URI and optional Gemini/Meta credentials
python app.py
```

Then open http://127.0.0.1:5002 for the bare test page, or hit the API
directly, e.g.:

```bash
curl http://127.0.0.1:5002/api/health
```

Start the persistent worker in another terminal:

```bash
source venv/bin/activate
python scripts/ai_worker.py
```

The worker polls MongoDB every five seconds by default and processes one job
at a time. Set `SAVEDFLOW_WORKER_POLL_SECONDS` to change the interval. Jobs
remain queued while it is offline and resume when it starts.

### Environment variables (`.env`)

| Variable                          | Required                        | Purpose                                                        |
| --------------------------------- | ------------------------------- | -------------------------------------------------------------- |
| `FLASK_ENV`                       | no                              | `development` or `production`                                  |
| `FLASK_SECRET_KEY`                | recommended                     | Flask session/signing key                                      |
| `MONGO_URI`                       | yes                             | MongoDB connection string                                      |
| `MONGO_DB_NAME`                   | yes                             | Database name                                                  |
| `META_APP_ID` / `META_APP_SECRET` | no                              | Only needed for the official API's own-media fetch             |
| `META_ACCESS_TOKEN`               | no                              | Long-lived Meta Graph API access token                         |
| `INSTAGRAM_ACCOUNT_ID`            | no                              | Your connected IG business/creator account id                  |
| `GEMINI_API_KEY`                  | no (but needed for AI analysis) | Gemini API key                                                 |
| `GEMINI_MODEL`                    | no                              | Defaults to `gemini-2.5-flash`                                 |
| `GEMINI_DAILY_REQUEST_LIMIT`      | no                              | Maximum outbound Gemini requests per UTC day; defaults to `20` |
| `SAVEDFLOW_WORKER_POLL_SECONDS`   | no                              | Worker poll interval; defaults to 5 seconds                    |
| `SAVEDFLOW_WORKER_TOKEN`          | for HTTP worker endpoint        | Worker endpoint shared secret                                  |
| `SAVEDFLOW_SYNC_TOKEN`            | for local sync agent            | Sync endpoint shared secret                                    |

Secrets are **never** sent to the frontend, logged, or hardcoded anywhere.

### Obtaining Meta/Instagram credentials

1. Create a Meta developer app at developers.facebook.com.
2. Connect an Instagram **business or creator** account (personal accounts
   are not supported by the Graph API).
3. Generate a long-lived access token with the relevant
   `instagram_basic`/`pages_show_list` style permissions.
4. Note again: this grants access to **your own published media and
   account info**, not your private Saved collection.

### Gemini setup

Create a Gemini API key and put it in `GEMINI_API_KEY`. The server keeps
this key; browser clients and local sync requests do not receive it.

## 6. How AI analysis works

1. The user explicitly requests analysis for an item. Importing saved
   metadata does not create an AI job.
2. The worker reuses saved evidence where available. Without evidence, the
   analysis is explicitly based on metadata or a supplied transcript.
3. `services/ai/prompts.py` builds a system prompt that explicitly tells
   the model to treat the caption/transcript as **untrusted data**, not
   instructions (prevents prompt injection from a video's own caption).
4. `services/ai/client.py` is the only file that imports the Gemini SDK,
   requests JSON output, and returns the raw text.
5. `services/ai/analyzer.py::validate_structured_output` validates every
   field of the schema (types, required list fields, 0-100 score ranges,
   valid enums for `difficulty`/`recommendation`) before anything is
   stored. Invalid output never reaches MongoDB - the job is marked
   `FAILED` with the validation error instead.
6. The HTTP route queues a MongoDB job and returns immediately. The persistent
   worker atomically claims one job at a time; poll it via `GET /api/jobs/<id>`.

## 7. How ranking works

`services/ai/ranking.py::compute_overall_score` is a deterministic,
documented formula:

```
overall = 0.30 * development_relevance_score
        + 0.25 * implementation_value_score
        + 0.20 * practicality_score
        + 0.15 * learning_value_score
        + 0.10 * originality_score
        + personal_relevance_bonus
        - already_watched_penalty (5)
        - already_applied_penalty (15)
```

clamped to `[0, 100]`. Every recommendation response includes the
breakdown that produced its score, plus a human-readable `reason` string.

## 8. How personalization works

`user_preferences` stores a `{topic, weight}` pair per category, weight in
`[0, 1]`, starting at `0.5`. Marking content in a topic useful/not-useful
nudges its weight by a fixed `±0.1` step (`PATCH /api/preferences` with
`was_useful`). The weight feeds `personal_relevance_bonus` in ranking. No
opaque ML model - the whole mechanism is inspectable in
`services/ai/recommendations.py`.

## 9. Running tests

```bash
pytest -q
```

No real MongoDB, Gemini, or Meta credentials are needed - MongoDB is
replaced by `mongomock`, and Gemini calls are mocked via `monkeypatch` in
`tests/test_ai.py`.

## 10. API reference

All responses are JSON. All errors follow:

```json
{
  "success": false,
  "error": { "code": "SOME_CODE", "message": "human readable message" }
}
```

### Health

**GET `/api/health`**
Response: `{"status": "ok", "database": "connected", "ai_configured": bool, "instagram_configured": bool}`

### Items

**GET `/api/items`**
Query params: `status`, `category`, `recommendation`, `watched` (`true`/`false`), `useful` (`true`/`false`), `min_score`, `search`, `sort` (`usefulness`|`created_at`|`oldest`|`date_added`|`development_relevance`), `page`, `page_size`.
Response: `{"success": true, "items": [...], "pagination": {"page", "page_size", "total"}}`

**GET `/api/items/<id>`** → `{"success": true, "item": {...}}`
Errors: `INVALID_ITEM_ID` (400), `ITEM_NOT_FOUND` (404)

**POST `/api/items`**
Body: `{"url": "https://www.instagram.com/reel/ABC123/", "caption": "...", "creator_username": "...", "category": "...", "tags": [...], "user_notes": "...", "why_saved": "..."}`
Response: `201` `{"success": true, "item": {...}}`
Errors: `INVALID_INSTAGRAM_URL` (400), `DUPLICATE_URL` (409)

**PATCH `/api/items/<id>`**
Body: any of `status`, `priority`, `category`, `tags`, `user_notes`, `why_saved`, `creator_username`, `caption`.
Errors: `INVALID_STATUS`, `INVALID_PRIORITY`, `NO_UPDATABLE_FIELDS` (400)

**DELETE `/api/items/<id>`** → `{"success": true, "deleted_id": "..."}`

**POST `/api/items/<id>/watch`** → increments `watch_count`, sets `watched_at`/`last_watched_at`, transitions `NEW` → `WATCHED`.

**POST `/api/items/<id>/apply`**
Body (optional): `{"implementation_notes": "...", "create_action": true, "action_title": "..."}`
Sets `status = APPLIED`, `applied_at`; optionally creates a linked action.

### Import

**POST `/api/import/manual`**
Body: `{"urls": ["https://www.instagram.com/reel/ABC/", "..."]}`
Response: `{"success": true, "total_submitted": N, "imported": N, "duplicates": N, "invalid": N, "invalid_items": [...], "imported_ids": [...]}`
Errors: `MISSING_FIELDS` (400)

**POST `/api/import/export`**
Body: the parsed JSON content of an Instagram data export file.
Response: `{"success": true, "format_supported": bool, "reason": str|null, "result": {...same shape as manual import...}}`

**POST `/api/import/instagram`**
No body needed. Always reports the Saved-collection limitation honestly (see section 2).

**GET `/api/import/status`** → counts of items by `source_method`, plus configuration flags.

### AI analysis & jobs

**POST `/api/items/<id>/analyze`** → `202` `{"success": true, "job": {...}}` (returns a queued job)

**POST `/api/items/<id>/reanalyze`** → same shape, always creates a new analysis version, preserving previous ones.

**GET `/api/items/<id>/analysis`** → `{"success": true, "analysis": {...full structured schema from section 12...}}`
Errors: `ANALYSIS_NOT_FOUND` (404)

**GET `/api/jobs/<id>`** → `{"success": true, "job": {"status": "QUEUED"|"PROCESSING"|"COMPLETED"|"FAILED", "error": str|null, ...}}`

### Actions

**GET `/api/actions`** - filters: `status`, `item_id`
**POST `/api/actions`** - body: `{"item_id", "title", "description", "priority", "due_date"}`
**GET `/api/actions/<id>`**
**PATCH `/api/actions/<id>`** - any of `title`, `description`, `priority`, `status`, `due_date`, `notes`, `result`, `rating`. Setting `status: "COMPLETED"` auto-stamps `completed_at`.

### Recommendations

**GET `/api/recommendations`** - overall ranked list
**GET `/api/recommendations/watch`** - `WATCH_NEXT`: unwatched items ranked by score
**GET `/api/recommendations/implement`** - `IMPLEMENT_NEXT`: un-applied items with actionable steps, each with a `suggested_action`

All three accept `?limit=N` (default 20, max 100) and return entries shaped
like:

```json
{"item_id": "...", "item": {...}, "score": 94, "reason": "..."}
```

### Dashboard

**GET `/api/dashboard`** → item/action counts plus `top_recommendations`, `recently_imported`, `recently_watched`, `recently_applied` - all computed live from MongoDB.

### Preferences

**GET `/api/preferences`**
**PATCH `/api/preferences`** - body: `{"topic": "MongoDB", "was_useful": true}` (nudges weight by ±0.1) or `{"topic": "MongoDB", "weight": 0.9}` (sets directly).

### Weekly review

**POST `/api/weekly-review`** - generates a review from the last 7 days of real data (imports, watches, applies, top categories, top items) plus an AI-written narrative summary if `GEMINI_API_KEY` is configured, otherwise a simple templated one.
**GET `/api/weekly-review/<id>`**

## 11. Database indexes

Created on startup (`extensions.py::_create_indexes`) if MongoDB is
reachable; startup does not crash if it isn't (health check will simply
report `database: "disconnected"` until MongoDB comes up):

- `instagram_items`: unique+sparse on `normalized_url` and
  `instagram_media_id`, plus `status`, `analysis_status`, `category`,
  `tags`, `created_at`, `usefulness_score`,
  `development_relevance_score`, `recommendation`.
- `actions`: `item_id`, `status`.
- `ai_jobs`: `item_id`, `status`.
- `ai_analyses`: `item_id`.
- `user_preferences`: unique on `topic`.
- `weekly_reviews`: `created_at`.

## 12. Troubleshooting

- **`database: "disconnected"` from `/api/health`**: MongoDB isn't
  reachable at `MONGO_URI`. Start MongoDB or fix the URI.
- **`ai_configured: false`**: `GEMINI_API_KEY` isn't set in `.env`.
  Analysis jobs will fail with a clear `GEMINI_API_KEY is not configured.`
  error rather than hanging or faking a result.
- **Analysis job stuck at `QUEUED`**: start `python scripts/ai_worker.py` and
  check worker logs. Stale `PROCESSING` job recovery is not yet implemented.
- **`INVALID_INSTAGRAM_URL`**: only `instagram.com/reel/...`,
  `/reels/...`, `/p/...`, and `/tv/...` links are recognized.

## 13. Security considerations

- Secrets only ever come from `.env` (never hardcoded, logged, or
  returned in any API response).
- `.env` is git-ignored.
- Video captions/transcripts are treated as **untrusted content** by the
  AI system prompt - they cannot override analysis instructions.
- All error responses use consistent, generic error codes/messages and
  never leak stack traces or credentials.

## 14. Production and current limitations

The repository has no browser-based frontend, authentication system, or
deployment manifest for a persistent backend. Vercel can host a frontend,
but Flask, MongoDB connectivity, authenticated browser capture, and the
long-running worker need a persistent backend/worker host. Configure TLS,
network access, secrets, and backups before production; this project has not
been deployed or connected to production infrastructure.

The local Instagram sync profile and `.env` contain sensitive session data
and must stay out of Git. Importing stores discovered metadata and thumbnails;
it does not enqueue AI analysis. Analysis must be requested for an individual
item. Adding a Reel to personal curation (if supported by a future UI) is a
separate preference; deleting from SavedFlow does not unsave it on Instagram.

- Stale `PROCESSING` job recovery and a bounded retry API are not implemented.
- A browser-based Useful/library experience is not implemented in this API repo.
- Authentication and per-user isolation are absent; deployment assumes a
  trusted single-user environment and should be protected at the network layer.

## 15. Future improvements

- A durable job queue (Redis/Celery) instead of in-process threads, for
  multi-worker deployments.
- Embedding-based similarity search instead of the current Jaccard-overlap
  duplicate detector, if/when the simple heuristic proves insufficient.
- A real frontend (this repo intentionally has none beyond a bare test
  page).
- Multi-user support (schema is written to be extensible toward this, but
  V1 assumes a single user).
  script to run in local dev-
  python scripts/instagram_saved_sync.py \
   --profile ./local-instagram-profile \
   --saved-url https://www.instagram.com/shaziazameer.dev/saved/all-posts/ \
   --server http://127.0.0.1:5001

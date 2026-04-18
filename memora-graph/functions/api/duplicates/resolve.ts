/**
 * POST /api/duplicates/resolve — record a user action on a duplicate pair.
 *
 * Body: { action: 'merge' | 'supersede_a' | 'supersede_b' | 'keep_both' | 'dismiss',
 *         a_id: number, b_id: number }
 *
 * All four actions mark the pair as resolved in `duplicate_resolutions` so it
 * stops appearing in `GET /api/duplicates`. The `action` value is kept as an
 * audit trail and also written to `memories_actions` for the History tab.
 *
 * Block 4 scope: UI-level resolution only. We do NOT mutate the underlying
 * `memories` / `memories_crossrefs` tables — merging content or writing
 * supersedes edges into the crossref graph is intentionally deferred; users
 * who want that can run the MCP `memory_merge` / `memory_link` tools.
 */

interface Env {
  DB_MEMORA: D1Database;
  DB_OB1: D1Database;
  DEFAULT_DB?: string;
}

interface ResolveBody {
  action?: string;
  a_id?: number;
  b_id?: number;
}

const VALID_ACTIONS = new Set(["merge", "supersede_a", "supersede_b", "keep_both", "dismiss"]);

function getDatabase(env: Env, dbName: string | null): D1Database {
  const name = dbName || env.DEFAULT_DB || "memora";
  if (name === "ob1") return env.DB_OB1;
  return env.DB_MEMORA;
}

async function ensureTables(db: D1Database): Promise<void> {
  // Lazy migration — safe to call on every request. `duplicate_resolutions`
  // stores one row per resolved (lo_id, hi_id) pair. UNIQUE constraint means
  // re-resolving a pair overwrites the prior entry via INSERT OR REPLACE.
  await db.prepare(
    "CREATE TABLE IF NOT EXISTS duplicate_resolutions (" +
      "  lo_id INTEGER NOT NULL," +
      "  hi_id INTEGER NOT NULL," +
      "  action TEXT NOT NULL," +
      "  resolved_at TEXT NOT NULL DEFAULT (datetime('now'))," +
      "  PRIMARY KEY (lo_id, hi_id)" +
      ")"
  ).run();
  // memories_actions is created by sync-to-d1 but not guaranteed; ensure it.
  await db.prepare(
    "CREATE TABLE IF NOT EXISTS memories_actions (" +
      "  id INTEGER PRIMARY KEY AUTOINCREMENT," +
      "  memory_id INTEGER," +
      "  action TEXT NOT NULL," +
      "  summary TEXT NOT NULL," +
      "  timestamp TEXT NOT NULL DEFAULT (datetime('now'))" +
      ")"
  ).run();
}

export const onRequestPost: PagesFunction<Env> = async ({ env, request }) => {
  const url = new URL(request.url);
  const dbName = url.searchParams.get("db");
  const db = getDatabase(env, dbName);

  let body: ResolveBody;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid json body" }, { status: 400 });
  }

  const action = body.action;
  const aId = body.a_id;
  const bId = body.b_id;

  if (!action || !VALID_ACTIONS.has(action)) {
    return Response.json(
      { error: `invalid action — expected one of ${Array.from(VALID_ACTIONS).join(", ")}` },
      { status: 400 }
    );
  }
  if (!Number.isFinite(aId) || !Number.isFinite(bId)) {
    return Response.json({ error: "a_id and b_id must be numbers" }, { status: 400 });
  }
  if (aId === bId) {
    return Response.json({ error: "a_id and b_id must differ" }, { status: 400 });
  }

  const lo = Math.min(aId as number, bId as number);
  const hi = Math.max(aId as number, bId as number);

  try {
    await ensureTables(db);

    // Upsert the resolution. INSERT OR REPLACE lets the user change their
    // mind (e.g. dismiss → supersede_a) without first deleting the row.
    await db.prepare(
      "INSERT OR REPLACE INTO duplicate_resolutions (lo_id, hi_id, action, resolved_at) " +
        "VALUES (?, ?, ?, datetime('now'))"
    ).bind(lo, hi, action).run();

    // Log to memories_actions for the History tab. We attach the action to
    // the "loser" side (for supersede_*/merge) or lo for neutral actions,
    // so it shows up when the user browses either memory's history.
    let attachedTo: number;
    let summary: string;
    switch (action) {
      case "supersede_a":
        // a is the newer winner; b (the other id) is superseded
        attachedTo = aId === lo ? hi : lo; // the non-a id
        summary = `Marked as superseded by #${aId}`;
        break;
      case "supersede_b":
        attachedTo = bId === lo ? hi : lo; // the non-b id
        summary = `Marked as superseded by #${bId}`;
        break;
      case "merge":
        // Merge-into-newer: we pick the higher id as "newer" (good enough
        // without a created_at lookup; it matches insertion order in D1).
        attachedTo = lo;
        summary = `Marked as merged into #${hi}`;
        break;
      case "keep_both":
        attachedTo = lo;
        summary = `Pair #${lo} ↔ #${hi} marked as not a duplicate`;
        break;
      case "dismiss":
      default:
        attachedTo = lo;
        summary = `Pair #${lo} ↔ #${hi} dismissed from duplicate review`;
        break;
    }

    await db.prepare(
      "INSERT INTO memories_actions (memory_id, action, summary, timestamp) " +
        "VALUES (?, ?, ?, datetime('now'))"
    ).bind(attachedTo, `duplicate:${action}`, summary).run();

    return Response.json({ ok: true, lo_id: lo, hi_id: hi, action });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return Response.json({ error: msg }, { status: 500 });
  }
};

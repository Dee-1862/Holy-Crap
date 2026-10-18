// A tiny shared key value store for hosts without a writable disk (Vercel). Uses Upstash Redis over its REST API,
// which is what Vercel's KV / Upstash integration provides, so no extra package is needed. Connect a store in the
// Vercel project (Storage, Upstash Redis) and it sets KV_REST_API_URL and KV_REST_API_TOKEN by itself.
// Without those variables kvEnabled is false and callers keep their local file or memory instead.

const URL_ = process.env.KV_REST_API_URL ?? process.env.UPSTASH_REDIS_REST_URL ?? "";
const TOKEN = process.env.KV_REST_API_TOKEN ?? process.env.UPSTASH_REDIS_REST_TOKEN ?? "";
export const kvEnabled = !!(URL_ && TOKEN);

async function call<T>(command: (string | number)[]): Promise<T | null> {
  if (!kvEnabled) return null;
  try {
    const r = await fetch(URL_, {
      method: "POST",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify(command),
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (!r.ok) return null;
    return ((await r.json()) as { result: T }).result;
  } catch {
    return null;
  }
}

export async function kvGet<T>(key: string): Promise<T | null> {
  const raw = await call<string | null>(["GET", key]);
  if (!raw) return null;
  try { return JSON.parse(raw) as T; } catch { return null; }
}

export async function kvSet(key: string, value: unknown, ttlSeconds?: number): Promise<void> {
  await call(ttlSeconds ? ["SET", key, JSON.stringify(value), "EX", ttlSeconds] : ["SET", key, JSON.stringify(value)]);
}

// A queue of small messages, oldest first, used to hand Crash presses from the website to the bridge.
export async function kvPush(key: string, value: unknown): Promise<void> {
  await call(["RPUSH", key, JSON.stringify(value)]);
  await call(["EXPIRE", key, 120]);
}
export async function kvDrain<T>(key: string): Promise<T[]> {
  const items = (await call<string[]>(["LRANGE", key, 0, -1])) ?? [];
  if (items.length) await call(["LTRIM", key, items.length, -1]);
  return items.flatMap((x) => { try { return [JSON.parse(x) as T]; } catch { return []; } });
}

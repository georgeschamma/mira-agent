import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import type { RuntimeConfigResponse } from "./types";

let cachedClient: SupabaseClient | null = null;
let cachedConfigKey: string | null = null;

export function getSupabaseClient(config: RuntimeConfigResponse): SupabaseClient {
  const configKey = `${config.supabase_url}:${config.supabase_anon_key}`;
  if (!cachedClient || cachedConfigKey !== configKey) {
    cachedClient = createClient(config.supabase_url, config.supabase_anon_key);
    cachedConfigKey = configKey;
  }
  return cachedClient;
}

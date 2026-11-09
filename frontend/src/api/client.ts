import createClient from "openapi-fetch";

import type { paths } from "./schema";

export function createApi(baseUrl = "") {
  return createClient<paths>({ baseUrl });
}

export type Api = ReturnType<typeof createApi>;

export const api = createApi();

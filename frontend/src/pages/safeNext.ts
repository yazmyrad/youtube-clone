/**
 * Where to go after signing in. `next` comes from the URL, so anyone can craft it: only a path
 * on this site is accepted. `//evil.test` and `/\evil.test` are links to other sites, and
 * browsers strip tabs and newlines before they parse a URL.
 */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || /^\/\/|\\|[\u0000-\u001f]/.test(next)) return "/";
  return next;
}

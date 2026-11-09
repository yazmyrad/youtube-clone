const FALLBACK = "Something went wrong. Please try again.";

/** Text to show for an API error body: `{detail: string}`, or FastAPI's 422 list of problems. */
export function errorMessage(error: unknown, fallback = FALLBACK): string {
  if (typeof error !== "object" || error === null || !("detail" in error)) return fallback;
  const { detail } = error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first: unknown = detail[0];
    if (typeof first === "object" && first !== null && "msg" in first) {
      if (typeof first.msg === "string") return first.msg;
    }
  }
  return fallback;
}

/** Text to show for something thrown. A TypeError is fetch failing to reach the server, and
 * its text isn't for visitors. */
export function failureMessage(failure: unknown): string {
  const isReadable = failure instanceof Error && !(failure instanceof TypeError);
  return isReadable ? failure.message : FALLBACK;
}

import type { Api } from "./client";
import type { Session } from "./session";

const SIGN_OUT_FAILED = "Couldn't sign out. Please try again.";

/** The session ends only once the server has revoked it: otherwise a reload would bring it
 * back, on what the user believes is a signed-out computer. */
export async function signOut(client: Api, session: Session): Promise<void> {
  const { response } = await client.POST("/api/auth/logout");
  if (!response.ok) throw new Error(SIGN_OUT_FAILED);
  session.clear();
}

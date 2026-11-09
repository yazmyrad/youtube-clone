import type { Api } from "./client";
import { errorMessage } from "./errors";
import type { components } from "./schema";
import type { Session } from "./session";

type LoginIn = components["schemas"]["LoginIn"];
type RegisterIn = components["schemas"]["RegisterIn"];

const SIGN_OUT_FAILED = "Couldn't sign out. Please try again.";
const CREATED_NOT_SIGNED_IN =
  "Your account was created, but we couldn't sign you in. Please sign in.";

/** Once the account exists, a failure to sign in must not read as a failure to create it:
 * registering again would only report that the name is taken. */
export async function registerAndSignIn(
  client: Api,
  account: RegisterIn,
  login: (credentials: LoginIn) => Promise<void>,
): Promise<void> {
  const { data, error } = await client.POST("/api/auth/register", { body: account });
  if (!data) throw new Error(errorMessage(error));
  try {
    await login({ email: account.email, password: account.password });
  } catch {
    throw new Error(CREATED_NOT_SIGNED_IN);
  }
}

/** The session ends only once the server has revoked it: otherwise a reload would bring it
 * back, on what the user believes is a signed-out computer. */
export async function signOut(client: Api, session: Session): Promise<void> {
  const { response } = await client.POST("/api/auth/logout");
  if (!response.ok) throw new Error(SIGN_OUT_FAILED);
  session.clear();
}

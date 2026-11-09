import type { RouteObject } from "react-router-dom";

import { App } from "./App";

/** A data router, which `useBlocker` requires. The routes themselves stay in `App`. */
export const appRoutes: RouteObject[] = [{ path: "*", element: <App /> }];

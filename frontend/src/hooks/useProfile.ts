import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import { errorMessage } from "../api/errors";
import type { components } from "../api/schema";
import { ME_KEY, type Me } from "./useAuth";

type MeUpdate = components["schemas"]["MeUpdateIn"];
export type ImageKind = "avatar" | "banner";

/** What the server takes; checked here first, so a wrong file fails at once. */
export const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const MAX_IMAGE_BYTES = 6 * 1024 * 1024;

export function imageProblem(file: File): string | null {
  if (!IMAGE_TYPES.includes(file.type)) return "Choose a JPEG, PNG or WebP image.";
  if (file.size > MAX_IMAGE_BYTES) return "Choose an image of at most 6 MB.";
  return null;
}

/** The channel's name, picture and banner show up everywhere: on every card and comment. */
function changed(queryClient: QueryClient, me: Me) {
  queryClient.setQueryData(ME_KEY, me);
  void queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (update: MeUpdate) => {
      const { data, error } = await api.PATCH("/api/users/me", { body: update });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    onSuccess: (me) => changed(queryClient, me),
  });
}

export function useChannelImage(kind: ImageKind) {
  const queryClient = useQueryClient();
  const params = { path: { kind } };
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const problem = imageProblem(file);
      if (problem) throw new Error(problem);
      const { data, error } = await api.PUT("/api/users/me/images/{kind}", {
        params,
        // The file itself is the body, sent as it is.
        body: file as unknown as string,
        bodySerializer: (body: unknown) => body as BodyInit,
        headers: { "Content-Type": file.type },
      });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    onSuccess: (me) => changed(queryClient, me),
  });
  const remove = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.DELETE("/api/users/me/images/{kind}", { params });
      if (!data) throw new Error(errorMessage(error));
      return data;
    },
    onSuccess: (me) => changed(queryClient, me),
  });
  return { upload, remove };
}

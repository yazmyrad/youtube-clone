import { useQueryClient } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";

import { MyVideos } from "../components/MyVideos";
import { UploadForm } from "../components/UploadForm";
import { useAuth } from "../hooks/useAuth";
import { MY_VIDEOS_KEY } from "../hooks/useMyVideos";

export function UploadPage() {
  const { user, isLoading } = useAuth();
  const queryClient = useQueryClient();

  if (isLoading) return null;
  if (!user) return <Navigate to="/login?next=/upload" replace />;

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-4 sm:p-6">
      <section>
        <h1 className="text-2xl font-medium">Upload video</h1>
        <UploadForm
          onUploaded={() => void queryClient.invalidateQueries({ queryKey: MY_VIDEOS_KEY })}
        />
      </section>
      <section>
        <h2 className="mb-2 text-xl font-medium">Your videos</h2>
        <MyVideos />
      </section>
    </div>
  );
}

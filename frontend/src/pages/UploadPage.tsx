import { Navigate } from "react-router-dom";

import { UploadForm } from "../components/UploadForm";
import { useAuth } from "../hooks/useAuth";

export function UploadPage() {
  const { user, isLoading } = useAuth();

  if (isLoading) return null;
  if (!user) return <Navigate to="/login?next=/upload" replace />;

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-4 sm:p-6">
      <section>
        <h1 className="text-2xl font-medium">Upload video</h1>
        <UploadForm />
      </section>
    </div>
  );
}

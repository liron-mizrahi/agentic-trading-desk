"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function GuideRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/pipelines/guide");
  }, [router]);
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="text-center">
        <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-accent-blue border-t-transparent" />
        <p className="mt-3 text-sm text-text-muted">Redirecting to Strategy Guide...</p>
      </div>
    </div>
  );
}

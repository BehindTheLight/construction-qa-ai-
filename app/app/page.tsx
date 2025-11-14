"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to chat page
    router.push("/chat");
  }, [router]);

  return (
    <div className="h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-2">Demo</h1>
        <p className="text-gray-500">Redirecting to chat...</p>
      </div>
    </div>
  );
}


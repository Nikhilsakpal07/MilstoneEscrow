"use client";

import dynamic from "next/dynamic";

const PlatformApp = dynamic(() => import("@/src/App"), {
  ssr: false,
  loading: () => (
    <div className="min-h-screen bg-black flex items-center justify-center text-zinc-400">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
        <span className="text-xs uppercase tracking-widest text-zinc-500 font-mono">
          Loading Multi-Sig Governance...
        </span>
      </div>
    </div>
  ),
});

export default function AdminPage() {
  return <PlatformApp initialScreen="admin" />;
}

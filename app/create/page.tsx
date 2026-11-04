"use client";

import dynamic from "next/dynamic";

const PlatformApp = dynamic(() => import("@/src/App"), {
  ssr: false,
  loading: () => (
    <div className="min-h-screen bg-black flex items-center justify-center text-zinc-400">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
        <span className="text-xs uppercase tracking-widest text-zinc-500 font-mono">
          Loading Escrow Studio...
        </span>
      </div>
    </div>
  ),
});

export default function CreateBountyPage() {
  return <PlatformApp initialScreen="studio" />;
}

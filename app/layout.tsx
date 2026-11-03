import "./globals.css";
import React from "react";
import Link from "next/link";
import Providers from "./Providers";

export const metadata = {
  title: "MilestoneEscrow - Freelance AI Escrow Platform",
  description: "Autonomous freelance escrow powered by PayPal and AI code verification",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 min-h-screen flex flex-col font-sans">
        <header className="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-2xl font-black bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                MilestoneEscrow
              </span>
              <span className="text-xs px-2 py-0.5 font-semibold bg-blue-50 text-blue-700 border border-blue-200 rounded-full">
                Sandbox
              </span>
            </Link>

            <nav className="flex items-center gap-4">
              <Link
                href="/"
                className="text-sm font-medium text-slate-600 hover:text-blue-600 transition-colors px-3 py-1.5 rounded-lg hover:bg-slate-100"
              >
                Dashboard
              </Link>
              <Link
                href="/create"
                className="text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg shadow-sm transition-all shadow-blue-500/20"
              >
                + Create Bounty
              </Link>
            </nav>
          </div>
        </header>

        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Providers>{children}</Providers>
        </main>

        <footer className="bg-white border-t border-slate-200 py-6 text-center text-xs text-slate-500">
          MilestoneEscrow &copy; {new Date().getFullYear()} — Powered by PayPal Sandbox &amp; Google Antigravity Agent
        </footer>
      </body>
    </html>
  );
}


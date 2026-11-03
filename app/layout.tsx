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

            <nav className="flex items-center gap-3 sm:gap-4">
              <Link
                href="/"
                className="text-sm font-medium text-slate-600 hover:text-blue-600 transition-colors px-3 py-1.5 rounded-lg hover:bg-slate-100"
              >
                Dashboard
              </Link>
              <Link
                href="/admin"
                className="text-sm font-semibold text-amber-800 bg-amber-50 hover:bg-amber-100 border border-amber-300 transition-colors px-3 py-1.5 rounded-lg flex items-center gap-1.5"
              >
                <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                <span>Admin Multi-Sig</span>
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


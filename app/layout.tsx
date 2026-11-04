import "./globals.css";
import React from "react";
import Providers from "./Providers";

export const metadata = {
  title: "Milestone Escrow - Autonomous AI Verification & Settlement Protocol",
  description:
    "Enterprise-grade multi-milestone freelance escrow powered by PayPal Sandbox and Google Gemini 1.5 Pro.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-black text-white min-h-screen font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

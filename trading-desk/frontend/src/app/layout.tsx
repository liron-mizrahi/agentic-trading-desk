import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Trading Desk — War Room",
  description:
    "Real-time dashboard for AI-powered trading analysis with human-in-the-loop validation.",
};

export const viewport: Viewport = {
  themeColor: "#0d1117",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen bg-surface text-text-primary antialiased">
        <nav className="sticky top-0 z-50 border-b border-surface-border bg-surface-card/80 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-2.5 sm:px-6 lg:px-8">
            <a href="/" className="text-sm font-semibold text-text-primary hover:text-accent-blue transition-colors">
              📈 Agentic Trading Desk
            </a>
            <div className="flex items-center gap-4">
              <a href="/" className="text-xs text-text-muted hover:text-text-secondary transition-colors border-b-2 border-transparent hover:border-accent-blue pb-0.5">
                War Room
              </a>
              <a href="/strategies" className="text-xs text-text-muted hover:text-text-secondary transition-colors border-b-2 border-transparent hover:border-accent-blue pb-0.5">
                Strategies
              </a>
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}

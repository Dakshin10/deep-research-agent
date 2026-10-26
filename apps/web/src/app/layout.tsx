import React from 'react';
import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Deep Research Agent',
  description: 'Single unified Claude-style AI assistant with parallel research fan-out, Cloudflare Code Mode, and temporal graph memory.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-foreground antialiased min-h-screen flex flex-col font-sans overflow-hidden">
        {children}
      </body>
    </html>
  );
}

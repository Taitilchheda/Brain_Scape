import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Brain_Scape Clinical Console",
  description: "Next.js-powered Brain_Scape clinical workspace",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" type="image/svg+xml" href="/brain-logo.svg" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700&family=Source+Sans+3:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
        <link rel="stylesheet" href="/legacy/brainscape.css" />
      </head>
      <body>{children}</body>
    </html>
  );
}

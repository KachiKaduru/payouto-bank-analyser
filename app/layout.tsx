import type { Metadata } from "next";
import { DM_Sans } from "next/font/google";
import "./_styles/globals.css";

const dmSans = DM_Sans({
  display: "swap",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Bank Analyser",
  description: "Analyse your bank statements",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${dmSans.className} antialiased`}>{children}</body>
    </html>
  );
}

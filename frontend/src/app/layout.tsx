import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RCAABUT Dashboard",
  description: "Course compact extraction and resource review dashboard"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

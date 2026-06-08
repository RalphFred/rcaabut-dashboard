"use client";

import Home from "../page";

type LayoutProps = {
  children: React.ReactNode;
};

export default function DashboardShellLayout({ children }: LayoutProps) {
  return <>{children}
    <Home />
  </>;
}

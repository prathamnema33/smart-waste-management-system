import type { Metadata } from "next";
import type { ReactNode } from "react";
import "leaflet/dist/leaflet.css";
import "./globals.css";
import "./segregation-map.css";

export const metadata: Metadata = {
  title: "Smart Waste Operations",
  description: "Municipal waste collection management platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en"><body>{children}</body></html>
  );
}

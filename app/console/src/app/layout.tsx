import type { Metadata, Viewport } from "next";
import { Instrument_Serif, Manrope } from "next/font/google";
import "./globals.css";

const display = Instrument_Serif({ weight: "400", subsets: ["latin"], variable: "--font-display", display: "swap" });
const body = Manrope({ subsets: ["latin"], variable: "--font-body", display: "swap" });

export const metadata: Metadata = {
  title: "Holy-Crap Console",
  description: "Poultry droppings health monitor. Demo data.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#d6f0ec",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <div className="bg" aria-hidden="true"><i /><i /><i /></div>
        {children}
      </body>
    </html>
  );
}

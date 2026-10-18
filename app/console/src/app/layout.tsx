import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

// Apple devices use the system font. Everywhere else the text is set in Geist, a clean and very readable sans.
const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });

export const metadata: Metadata = {
  title: "Holy-Crap Console",
  description: "Poultry droppings health monitor. Demo data.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#000000",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={geist.variable} suppressHydrationWarning>
      <head>
        {/* apply the saved theme before first paint */}
        <script dangerouslySetInnerHTML={{ __html: "try{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}catch(e){}" }} />
      </head>
      <body>
        <div className="bg" aria-hidden="true"><i /><i /><i /></div>
        {children}
      </body>
    </html>
  );
}

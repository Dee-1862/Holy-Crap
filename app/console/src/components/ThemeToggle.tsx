"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

// Switches between light (blue on blue) and dark (black with white glass).
// Starts from the saved choice, then the system setting. The saved choice is applied
// before first paint by the script in layout.tsx, so there is no flash.
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const current = document.documentElement.dataset.theme as Theme | undefined;
    setTheme(current ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  }, []);

  const flip = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch { /* private mode, ignore */ }
  };

  return (
    <button className="pill theme" onClick={flip} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
      {theme === "dark" ? "Dark" : "Light"}
    </button>
  );
}

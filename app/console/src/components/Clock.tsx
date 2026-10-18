"use client";

import { useEffect, useState } from "react";

// Renders after mount so the server and client markup match.
export default function Clock() {
  const [now, setNow] = useState("");
  useEffect(() => {
    const tick = () => setNow(new Date().toTimeString().slice(0, 5));
    tick();
    const id = window.setInterval(tick, 30000);
    return () => window.clearInterval(id);
  }, []);
  return <span className="pill num">{now || "00:00"}</span>;
}

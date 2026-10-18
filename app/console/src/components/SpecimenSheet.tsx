"use client";

import { useEffect } from "react";
import type { Specimen } from "@/lib/data";
import SpecimenCard from "./SpecimenCard";

// Detail sheet for one specimen. Dims the page behind it, closes with Done, Esc or a tap outside.
export default function SpecimenSheet({ specimen, onClose }: { specimen: Specimen; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <button className="scrim" aria-label="Close specimen" onClick={onClose} />
      <aside className="glass sheet" aria-label="Specimen detail">
        <button className="sheet-close" onClick={onClose}>Done</button>
        <SpecimenCard key={specimen.id} specimen={specimen} />
      </aside>
    </>
  );
}

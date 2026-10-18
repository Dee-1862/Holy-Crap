"use client";

import { useEffect, useRef } from "react";
import type { TypeKey } from "@/lib/data";
import { drawSpecimen } from "@/lib/specimen";

interface Props {
  type: TypeKey;
  region: [number, number];
  heat: boolean;
  seed: string;
  width?: number;
  height?: number;
  label: string;
}

export default function SpecimenCanvas({ type, region, heat, seed, width = 360, height = 270, label }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (ref.current) drawSpecimen(ref.current, type, region, heat, seed);
  }, [type, region, heat, seed]);
  return <canvas ref={ref} width={width} height={height} role="img" aria-label={label} />;
}

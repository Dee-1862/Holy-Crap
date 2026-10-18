import Link from "next/link";

type View = "map" | "live" | "edge";
const VIEWS: { id: View; label: string; href: string }[] = [
  { id: "map", label: "Map", href: "/" },
  { id: "edge", label: "Pi", href: "/edge" },
];

// Segmented control that switches between the views. The Live page has no tab, the map's camera links to it.
export default function ViewSwitch({ current }: { current: View }) {
  return (
    <nav className="seg" aria-label="Views">
      {VIEWS.map((v) => (v.id === current
        ? <span key={v.id} aria-current="page">{v.label}</span>
        : <Link key={v.id} href={v.href}>{v.label}</Link>))}
    </nav>
  );
}

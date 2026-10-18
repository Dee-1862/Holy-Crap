import Link from "next/link";

type View = "map" | "specimens" | "live" | "edge" | "mobile";
const VIEWS: { id: View; label: string; href: string }[] = [
  { id: "map", label: "Map", href: "/" },
  { id: "specimens", label: "Droppings", href: "/specimens" },
  { id: "edge", label: "Pi", href: "/edge" },
  { id: "mobile", label: "Phone", href: "/m" },
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

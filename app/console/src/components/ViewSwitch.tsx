import Link from "next/link";

type View = "map" | "specimens" | "mobile";
const VIEWS: { id: View; label: string; href: string }[] = [
  { id: "map", label: "Map", href: "/" },
  { id: "specimens", label: "Droppings", href: "/specimens" },
  { id: "mobile", label: "Phone", href: "/m" },
];

// Segmented control that switches between the three views.
export default function ViewSwitch({ current }: { current: View }) {
  return (
    <nav className="seg" aria-label="Views">
      {VIEWS.map((v) => (v.id === current
        ? <span key={v.id} aria-current="page">{v.label}</span>
        : <Link key={v.id} href={v.href}>{v.label}</Link>))}
    </nav>
  );
}

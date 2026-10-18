import { CAMERA } from "@/server/droppings";

// The droppings the cameras found and each camera's bird counts, for the dashboard (lib/store.ts).
export async function GET() {
  return Response.json(CAMERA, { headers: { "cache-control": "public, max-age=300" } });
}

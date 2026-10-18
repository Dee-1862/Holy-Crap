import { specimensFrom, type CameraSet } from "@/lib/data";
import DATA from "@/lib/camera-droppings.json";

// The camera set on the server, for the watch snapshot and to check specimen ids in actions.
export const CAMERA = DATA as unknown as CameraSet;
export const CAMERA_SPECIMENS = specimensFrom(CAMERA);

"""Explainability section: says in plain words what the patch shows and what the model said about it.

Receives patches from the model section (name hc/explain). It measures the patch itself, the part in the
middle where the spot is against the ring around it, so every reason can be checked on the picture:
    dark      how much darker the spot is than the floor around it
    red       share of the spot that is red, a blood cue
    green     share that is green, a bile cue
    white     share that is white, urates (a white cap is normal, none or all white is not)
These are appearance measurements, not a diagnosis. The model's class and score are reported next to them,
and when the model was not reachable the result says so instead of guessing.

The result goes to the watch, the dashboard and the cloud sections.
"""
from __future__ import annotations

import base64
import json
import time

import qnxipc
from spotter import Link

NAMES = {"cocci": "coccidiosis", "healthy": "healthy", "ncd": "ncd", "salmo": "salmonella"}


def measure(rgb: bytes, side: int) -> dict:
    inner, ring = [], []
    c, r_in, r_out = side / 2, side * 0.18, side * 0.4
    for y in range(0, side, 2):
        for x in range(0, side, 2):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            k = (y * side + x) * 3
            px = rgb[k], rgb[k + 1], rgb[k + 2]
            if d < r_in:
                inner.append(px)
            elif d < r_out:
                ring.append(px)

    def lum(p):
        return (77 * p[0] + 150 * p[1] + 29 * p[2]) >> 8

    n = max(1, len(inner))
    li = sum(lum(p) for p in inner) / n
    lr = sum(lum(p) for p in ring) / max(1, len(ring))
    red = sum(1 for p in inner if p[0] > p[1] + 35 and p[0] > p[2] + 35) / n
    green = sum(1 for p in inner if p[1] > p[0] + 15 and p[1] > p[2] + 10) / n
    white = sum(1 for p in inner if min(p) > 175 and max(p) - min(p) < 40) / n
    return {"spot": round(li), "floor": round(lr), "dark": round(lr - li), "red": round(red, 3), "green": round(green, 3),
            "white": round(white, 3), "rgb": [round(sum(p[i] for p in inner) / n) for i in range(3)]}


def decide(m: dict, model: dict) -> tuple[str, str]:
    """alert, normal or dismissed, with the reason. Only alert and normal go to the watch.
    The detector learned on close-ups and also scores birds and labels, so its word alone is not enough."""
    if "error" in model:
        return "dismissed", "Not checked by the model"
    b = model["boxes"][0] if model.get("boxes") else None
    if not b:
        return "dismissed", "Model found no dropping here"
    bx, by = (b["box"][0] + b["box"][2]) / 2, (b["box"][1] + b["box"][3]) / 2
    size = max(b["box"][2] - b["box"][0], b["box"][3] - b["box"][1])
    if abs(bx - 0.5) > 0.25 or abs(by - 0.5) > 0.25:
        return "dismissed", "Model's box is not on the spot"
    if size > 0.5:
        return "dismissed", "Model's box is too big for a dropping"
    if m["white"] > 0.3:
        return "dismissed", "Mostly white, looks like a bird or feather"
    if m["dark"] < -10:                              # birds in these houses are lighter than the litter, droppings are not
        return "dismissed", "Lighter than the floor, likely part of a bird"
    if abs(m["dark"]) < 15:
        return "dismissed", "Barely stands out from the floor"
    if b["score"] < 0.6:
        return "dismissed", "Model is unsure"
    return ("normal" if b["cls"] == "healthy" else "alert"), "Passed every check"


def reasons(m: dict, model: dict) -> tuple[list[str], dict]:
    why = []
    if m["dark"] > 25:
        why.append(f"Spot is {m['dark']} levels darker than the floor around it")
    elif m["dark"] < -25:
        why.append(f"Spot is {-m['dark']} levels lighter than the floor around it")
    else:
        why.append("Spot barely stands out from the floor")
    if m["red"] > 0.08:
        why.append(f"{round(m['red'] * 100)}% of the spot is red, check for blood")
    if m["green"] > 0.08:
        why.append(f"{round(m['green'] * 100)}% of the spot is green")
    if m["white"] > 0.6:
        why.append("Mostly white, more likely a feather or urate than a dropping")
    elif m["white"] > 0.05:
        why.append(f"White cap on {round(m['white'] * 100)}% of it, urates look present")
    if "error" in model:
        why.insert(0, "Not checked by the model, it was not reachable")
    else:
        b = model["boxes"][0] if model.get("boxes") else None
        why.insert(0, f"Model: {NAMES[b['cls']]} at {round(b['score'] * 100)}%" if b else "Model found no dropping in this patch")
    # 0 to 10 like the dashboard's sub-scores, 10 looks normal. Only what the picture can show.
    sub = {"color": 10 - min(10, round(m["green"] * 40)), "urates": 8 if 0.05 < m["white"] < 0.6 else 4,
           "blood": 10 - min(10, round(m["red"] * 40))}
    return why[:4], sub


def main():
    watch, uplink, cloud = Link("hc/watch"), Link("hc/uplink"), Link("hc/cloud")

    def handle(msg: bytes) -> bytes:
        e = json.loads(msg)
        rgb = base64.b64decode(e["rgb"])
        t0 = time.perf_counter()
        m = measure(rgb, e["side"])
        why, sub = reasons(m, e["model"])
        verdict, because = decide(m, e["model"])
        b = e["model"].get("boxes", [None])[0] if e["model"].get("boxes") else None
        result = {"kind": "explained", "id": e["spot"]["id"], "t": e["t"], "cx": e["spot"]["cx"], "cy": e["spot"]["cy"],
                  "checked": "error" not in e["model"], "verdict": verdict, "because": because, "cls": NAMES[b["cls"]] if b else None,
                  "score": b["score"] if b else 0.0, "best": e["model"].get("best"), "measure": m, "why": why, "sub": sub,
                  "ms": round((time.perf_counter() - t0) * 1000, 1), "patch": e["rgb"], "side": e["side"],
                  "modelStats": e.get("stats")}
        uplink.send(result)
        small = {k: v for k, v in result.items() if k not in ("patch",)}
        if verdict != "dismissed":
            watch.send(small)
        cloud.send(small)
        return b"ok"

    qnxipc.Server("hc/explain").serve(handle)


if __name__ == "__main__":
    main()

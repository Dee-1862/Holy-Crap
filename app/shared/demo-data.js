// Filler data for the UI prototypes. Synthetic, not real model output.
/* ---------- demo data (synthetic, not real model output) ---------- */
const TYPES = {
  healthy:     { name: "Healthy",              color: "#7a4a22" },
  coccidiosis: { name: "Coccidiosis",          color: "#4a2418" },
  salmonella:  { name: "Salmonella",           color: "#c9b24a" },
  ncd:         { name: "Newcastle disease",    color: "#4fae4a" }
};
const GROUPS = [
  { id: "A1", name: "Pen A1", n: 24 }, { id: "A2", name: "Pen A2", n: 24 },
  { id: "B1", name: "Pen B1", n: 18 }, { id: "B2", name: "Pen B2", n: 18 },
  { id: "C1", name: "Cage row C1", n: 12 }, { id: "C2", name: "Cage row C2", n: 12 }
];
function mk(id, min, group, type, probs, grade, sub, region, why) {
  return { id, minsAgo: min, group, type, probs, grade, sub, region, why, state: "new" };
}
const EVENTS = [
  mk("E-0412", 2,  "B2", "coccidiosis", { healthy: .06, coccidiosis: .81, salmonella: .09, ncd: .04 }, 2, { color: 2, consistency: 3, urates: 4, blood: 1, foam: 8 }, [.42,.55],
     ["Dark red-brown streaking across the lower third", "Wet, mucus-like outline instead of a firm shape", "White urate cap is thin or missing", "Pattern repeated in 3 events from this group in 10 min"]),
  mk("E-0411", 6,  "B2", "coccidiosis", { healthy: .12, coccidiosis: .70, salmonella: .14, ncd: .04 }, 3, { color: 3, consistency: 4, urates: 5, blood: 2, foam: 8 }, [.55,.48],
     ["Dark brown with red tint near the center", "Soft edges, moderate moisture"]),
  mk("E-0410", 9,  "A1", "healthy",     { healthy: .93, coccidiosis: .03, salmonella: .03, ncd: .01 }, 9, { color: 9, consistency: 9, urates: 9, blood: 10, foam: 10 }, [.50,.42],
     ["Uniform brown body", "Firm shape with a distinct white urate cap", "No blood, foam or abnormal color"]),
  mk("E-0413", 11, "B2", "coccidiosis", { healthy: .10, coccidiosis: .66, salmonella: .18, ncd: .06 }, 3, { color: 3, consistency: 4, urates: 4, blood: 2, foam: 8 }, [.47,.52],
     ["Dark brown with red streaks", "Loose, watery edge", "Third abnormal specimen from this group in 15 minutes"]),
  mk("E-0409", 14, "C1", "salmonella",  { healthy: .22, coccidiosis: .08, salmonella: .60, ncd: .10 }, 4, { color: 4, consistency: 3, urates: 6, blood: 9, foam: 3 }, [.46,.60],
     ["Yellowish tint over most of the area", "Foamy texture with small bubbles", "Watery spread beyond the normal footprint"]),
  mk("E-0408", 21, "A2", "healthy",     { healthy: .88, coccidiosis: .05, salmonella: .05, ncd: .02 }, 8, { color: 8, consistency: 8, urates: 9, blood: 10, foam: 10 }, [.48,.50],
     ["Brown body, slightly moist", "White cap present"]),
  mk("E-0407", 33, "B1", "ncd",         { healthy: .20, coccidiosis: .05, salmonella: .15, ncd: .52 }, 3, { color: 2, consistency: 3, urates: 5, blood: 9, foam: 7 }, [.52,.46],
     ["Green tint across the specimen", "Watery consistency", "Low confidence, a second look is advised"]),
  mk("E-0406", 47, "C2", "healthy",     { healthy: .96, coccidiosis: .02, salmonella: .01, ncd: .01 }, 10, { color: 10, consistency: 10, urates: 9, blood: 10, foam: 10 }, [.50,.50],
     ["Textbook example of a firm brown dropping with a white cap"]),
  mk("E-0405", 62, "A1", "healthy",     { healthy: .90, coccidiosis: .04, salmonella: .04, ncd: .02 }, 8, { color: 8, consistency: 9, urates: 8, blood: 10, foam: 10 }, [.44,.52],
     ["Brown, firm", "White cap slightly smeared"])
];


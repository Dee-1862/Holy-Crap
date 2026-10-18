// Who runs the text alert program, shown on /privacy and /terms. Carriers check that these are real,
// so keep them current. Each can be overridden with an environment variable on Vercel.
export const LEGAL = {
  operator: process.env.NEXT_PUBLIC_LEGAL_OPERATOR ?? "the Holy-Crap team",
  email: process.env.NEXT_PUBLIC_LEGAL_EMAIL ?? "drb6015@psu.edu",
  program: "Holy-Crap Barn Alerts",
  effective: "October 18, 2026",
};

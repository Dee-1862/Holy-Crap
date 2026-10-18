// Who runs the text alert program, shown on /privacy and /terms. Carriers check that these are real,
// so fill them in before submitting the pages. Each can also be set as an environment variable on Vercel.
export const LEGAL = {
  operator: process.env.NEXT_PUBLIC_LEGAL_OPERATOR ?? "OPERATOR NAME",
  email: process.env.NEXT_PUBLIC_LEGAL_EMAIL ?? "CONTACT EMAIL",
  program: "Holy-Crap Barn Alerts",
  effective: "October 18, 2026",
};

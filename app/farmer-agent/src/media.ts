import fs from "node:fs";
import path from "node:path";
import type { AlertEvidence } from "./types";

export const MAX_EVIDENCE_BYTES = 5 * 1024 * 1024;

function contentTypeForExt(localPath: string): AlertEvidence["contentType"] | null {
  const ext = path.extname(localPath).toLowerCase();
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".png") return "image/png";
  return null;
}

// Validates a local evidence image and reads its bytes. Every error message is
// sanitized and never contains the file path.
export function loadEvidenceImage(
  localPath: string,
  sourceLabel = "Attached: Camera photo.",
): AlertEvidence {
  const contentType = contentTypeForExt(localPath);
  if (!contentType) {
    throw new Error("Evidence image must be a .jpg or .png file");
  }
  let stat: fs.Stats;
  try {
    stat = fs.statSync(localPath);
  } catch {
    throw new Error("Evidence image could not be found");
  }
  if (!stat.isFile()) {
    throw new Error("Evidence image is not a readable JPEG or PNG");
  }
  if (stat.size === 0) {
    throw new Error("Evidence image file is empty");
  }
  if (stat.size > MAX_EVIDENCE_BYTES) {
    throw new Error("Evidence image is too large; the limit is 5 MB");
  }
  let bytes: Buffer;
  try {
    bytes = fs.readFileSync(localPath);
  } catch {
    throw new Error("Evidence image is not a readable JPEG or PNG");
  }
  const validMagic = contentType === "image/jpeg"
    ? bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
    : bytes.length >= 8 && bytes.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  if (!validMagic) throw new Error("Evidence image is not a readable JPEG or PNG");
  const label = sourceLabel.trim();
  if (!label) throw new Error("Evidence image needs a plain source label");
  return {
    localPath,
    contentType,
    filename: path.basename(localPath),
    sizeBytes: stat.size,
    sourceLabel: label,
  };
}

export function readEvidenceBytes(evidence: AlertEvidence): Buffer {
  const current = loadEvidenceImage(evidence.localPath, evidence.sourceLabel);
  if (
    current.contentType !== evidence.contentType ||
    current.filename !== evidence.filename ||
    current.sizeBytes !== evidence.sizeBytes
  ) {
    throw new Error("Evidence image changed after the alert was created");
  }
  return fs.readFileSync(evidence.localPath);
}

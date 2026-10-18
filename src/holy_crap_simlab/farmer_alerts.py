"""Small localhost bridge from completed clip assessments to the farmer agent."""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Callable, Literal
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

from .models import ClipAssessment, NormalizedBoundingBox

FarmerAlertResult = Literal["sent", "skipped", "failed"]


class FarmerAlertNotifier:
    def __init__(
        self,
        url: str | None = None,
        *,
        pen_name: str | None = None,
        timeout_s: float = 30.0,
        enabled: bool | None = None,
        evidence_dir: Path | None = None,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        self.url = url or os.getenv(
            "HOLY_CRAP_FARMER_AGENT_URL",
            "http://127.0.0.1:4317/simulation-alerts",
        )
        self.pen_name = pen_name or os.getenv("HOLY_CRAP_ALERT_PEN_NAME", "Pen 6")
        self.timeout_s = timeout_s
        self.evidence_dir = Path(evidence_dir).resolve() if evidence_dir else None
        self.runner = runner
        self.enabled = (
            os.getenv("HOLY_CRAP_FARMER_ALERTS_ENABLED", "0").strip().lower()
            in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )

    def _save_evidence(
        self,
        assessment: ClipAssessment,
        video_path: Path | None,
        timestamp_s: float,
        bbox: NormalizedBoundingBox,
    ) -> dict[str, object] | None:
        if self.evidence_dir is None or video_path is None or not video_path.is_file():
            return None
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        output = self.evidence_dir / f"{assessment.id}.jpg"
        temporary = self.evidence_dir / f".{assessment.id}.part.jpg"
        command = [
            "ffmpeg", "-v", "error", "-ss", f"{timestamp_s:.3f}",
            "-i", str(video_path), "-frames:v", "1",
            "-vf", "scale='min(1280,iw)':-2", "-q:v", "2", "-y", str(temporary),
        ]
        try:
            completed = self.runner(command, check=False, capture_output=True, timeout=30)
            if completed.returncode != 0 or not temporary.is_file():
                return None
            with Image.open(temporary) as frame:
                image = frame.convert("RGB")
                width, height = image.size
                x0 = round(bbox.x * width)
                y0 = round(bbox.y * height)
                x1 = round((bbox.x + bbox.width) * width)
                y1 = round((bbox.y + bbox.height) * height)
                pad = max(10, round(min(width, height) * 0.015))
                box = (
                    max(0, x0 - pad),
                    max(0, y0 - pad),
                    min(width - 1, x1 + pad),
                    min(height - 1, y1 + pad),
                )
                draw = ImageDraw.Draw(image)
                line_width = max(4, round(min(width, height) * 0.008))
                draw.rectangle(box, outline=(255, 190, 0), width=line_width)
                label = "Camera flagged this"
                label_box = draw.textbbox((0, 0), label)
                label_width = label_box[2] - label_box[0]
                label_height = label_box[3] - label_box[1]
                label_x = box[0]
                label_y = max(0, box[1] - label_height - 12)
                draw.rectangle(
                    (label_x, label_y, label_x + label_width + 12, label_y + label_height + 8),
                    fill=(255, 190, 0),
                )
                draw.text((label_x + 6, label_y + 4), label, fill=(20, 20, 20))
                image.save(temporary, format="JPEG", quality=90)
            size = temporary.stat().st_size
            if size < 3 or size > 5 * 1024 * 1024:
                return None
            with temporary.open("rb") as handle:
                if handle.read(3) != b"\xff\xd8\xff":
                    return None
            temporary.replace(output)
            return {
                "localPath": str(output),
                "contentType": "image/jpeg",
                "filename": output.name,
                "sizeBytes": size,
                "sourceLabel": (
                    f"Frame from {self.pen_name} at {timestamp_s:.1f} seconds "
                    "in the assessed clip."
                ),
            }
        except (OSError, subprocess.SubprocessError):
            return None
        finally:
            temporary.unlink(missing_ok=True)

    def notify(
        self,
        assessment: ClipAssessment,
        *,
        video_path: Path | None = None,
    ) -> FarmerAlertResult:
        pen = assessment.summary.pen_assessment
        abnormal = [
            candidate
            for candidate in assessment.summary.feces.candidates
            if candidate.classification.product_label == "abnormal"
            and candidate.classification.label
        ]
        if pen is None or pen.state != "review" or not abnormal:
            return "skipped"
        if not self.enabled:
            return "failed"

        strongest = max(abnormal, key=lambda item: item.classification.confidence)
        end_s = assessment.video.segment_end_s or assessment.video.duration_s
        duration_s = max(0.0, (end_s or 0.0) - assessment.video.segment_start_s)
        payload = {
            "eventId": assessment.id,
            "penName": self.pen_name,
            "observationCount": len(abnormal),
            "windowMinutes": max(1, math.ceil(duration_s / 60)),
            "windowSeconds": max(0.001, round(duration_s, 3)),
            "confidence": strongest.classification.confidence,
            "suspectedIllness": strongest.classification.label,
            "createdAt": assessment.created_at.isoformat(),
        }
        evidence = self._save_evidence(
            assessment,
            video_path,
            strongest.timestamp_s,
            strongest.bbox,
        )
        if evidence is not None:
            payload["evidence"] = evidence
        request = Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
            return "sent" if body.get("status") == "sent" else "failed"
        except Exception:
            return "failed"

"""Small localhost bridge from completed clip assessments to the farmer agent."""

from __future__ import annotations

import json
import math
import os
from typing import Literal
from urllib.request import Request, urlopen

from .models import ClipAssessment

FarmerAlertResult = Literal["sent", "skipped", "failed"]


class FarmerAlertNotifier:
    def __init__(
        self,
        url: str | None = None,
        *,
        pen_name: str | None = None,
        timeout_s: float = 2.0,
        enabled: bool | None = None,
    ) -> None:
        self.url = url or os.getenv(
            "HOLY_CRAP_FARMER_AGENT_URL",
            "http://127.0.0.1:4317/simulation-alerts",
        )
        self.pen_name = pen_name or os.getenv("HOLY_CRAP_ALERT_PEN_NAME", "Pen 6")
        self.timeout_s = timeout_s
        self.enabled = (
            os.getenv("HOLY_CRAP_FARMER_ALERTS_ENABLED", "0").strip().lower()
            in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )

    def notify(self, assessment: ClipAssessment) -> FarmerAlertResult:
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
            "confidence": strongest.classification.confidence,
            "suspectedIllness": strongest.classification.label,
            "createdAt": assessment.created_at.isoformat(),
        }
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

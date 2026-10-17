# Mistakes & Dead Ends

Record anything that went wrong or was ruled out so we don't repeat it. Format: date, what happened, why, what to do instead.

- 2026-10-17: Assumed "multiple hens at once" meant per-hen monitoring. Droppings can't be attributed to individual hens from a floor camera. Plan is per-zone monitoring instead.
- 2026-10-17: Considered ESP32 as a QNX target. No evidence QNX supports ESP32; treat ESP32 as sensor/display nodes only (and it can't run the vision models).
- 2026-10-17: Research claims from the original write-up (UGA work, "AI4D" dataset name) are unverified. Don't cite them until checked.
- 2026-10-17: Wi-Fi coverage in a barn is an assumption, not verified. If alerts go missing in the field, check dead spots first, and make the StopWatch show an explicit "offline" state so silence is never mistaken for "all healthy".
- 2026-10-17: Over-recommended multiple Pis too early. Start with one; add more only when one camera can't cover the area.

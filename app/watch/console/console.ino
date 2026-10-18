// StopWatch console with filler data. Three pages, no Wi-Fi yet.
//   Page 0 HOME   barn status ring and the worst group
//   Page 1 GROUPS six groups with mean grade
//   Page 2 ALERT  one abnormal specimen at a time
// Buttons
//   B click           next page
//   A click           acknowledge (on ALERT) or jump to ALERT
//   A hold            false alarm
//   B hold ~1.5 s     escalate
// Touch
//   swipe left/right  change page
//   tap on ALERT      next alert
#include <M5Unified.h>

struct Ev { const char* id; const char* group; const char* type; uint8_t grade; uint8_t conf; uint8_t mins; bool bad; };
static const Ev EV[] = {
  {"E-0412", "B2", "COCCIDIOSIS", 2, 81, 2,  true },
  {"E-0411", "B2", "COCCIDIOSIS", 3, 70, 6,  true },
  {"E-0410", "A1", "HEALTHY",     9, 93, 9,  false},
  {"E-0413", "B2", "COCCIDIOSIS", 3, 66, 11, true },
  {"E-0409", "C1", "SALMONELLA",  4, 60, 14, true },
  {"E-0408", "A2", "HEALTHY",     8, 88, 21, false},
  {"E-0407", "B1", "NEWCASTLE",   3, 52, 33, true },
  {"E-0406", "C2", "HEALTHY",     10, 96, 47, false},
  {"E-0405", "A1", "HEALTHY",     8, 90, 62, false},
};
static const int NEV = sizeof(EV) / sizeof(EV[0]);
static const char* GROUPS[] = {"A1", "A2", "B1", "B2", "C1", "C2"};
static const int NG = 6;

static uint16_t C_OR, C_CY, C_RD, C_GR, C_WH, C_DK;
static const int CX = 233, CY = 233;
static int page = 0, alertIdx = 0;
static bool dirty = true;
static uint32_t toastUntil = 0, bStart = 0;
static bool bFired = false, arcShown = false;
static int tx0, ty0, tlx, tly;
static char toastMsg[40];

// ----- data helpers -----
static int badInGroup(const char* g) { int n = 0; for (int i = 0; i < NEV; i++) if (EV[i].mins <= 15 && EV[i].bad && !strcmp(EV[i].group, g)) n++; return n; }
static float meanGrade(const char* g, int* count) {
  int n = 0, sum = 0;
  for (int i = 0; i < NEV; i++) if (EV[i].mins <= 15 && !strcmp(EV[i].group, g)) { n++; sum += EV[i].grade; }
  *count = n; return n ? (float)sum / n : -1;
}
static int level(const char* g) { int b = badInGroup(g); return b >= 3 ? 2 : b >= 1 ? 1 : 0; }
static uint16_t levelColor(int l) { return l == 2 ? C_RD : l == 1 ? C_OR : C_CY; }
static uint16_t gradeColor(int g) { return g >= 8 ? C_CY : g >= 5 ? C_OR : C_RD; }
static int badCount() { int n = 0; for (int i = 0; i < NEV; i++) if (EV[i].bad) n++; return n; }
static int nthBad(int k) { int n = 0; for (int i = 0; i < NEV; i++) if (EV[i].bad) { if (n == k) return i; n++; } return 0; }

// ----- drawing helpers -----
static void txt(const char* s, int x, int y, uint16_t col, int size, textdatum_t d = middle_center) {
  M5.Display.setFont(&fonts::Font4);
  M5.Display.setTextSize(size);
  M5.Display.setTextDatum(d);
  M5.Display.setTextColor(col, C_DK);
  M5.Display.drawString(s, x, y);
}
static void small(const char* s, int x, int y, uint16_t col, textdatum_t d = middle_center) {
  M5.Display.setFont(&fonts::Font2);
  M5.Display.setTextSize(1);
  M5.Display.setTextDatum(d);
  M5.Display.setTextColor(col, C_DK);
  M5.Display.drawString(s, x, y);
}
static void dots() {
  for (int i = 0; i < 3; i++) {
    int x = CX - 20 + i * 20;
    M5.Display.fillCircle(x, 436, i == page ? 5 : 3, i == page ? C_OR : C_GR);
  }
}
static void ring(uint16_t col) { M5.Display.fillArc(CX, CY, 214, 224, 0, 360, col); }

static void pageHome() {
  int worst = -1, wl = 0;
  for (int i = 0; i < NG; i++) { int l = level(GROUPS[i]); if (l > wl || (l == wl && l > 0 && worst < 0)) { wl = l; worst = i; } }
  int alerting = 0; for (int i = 0; i < NG; i++) if (level(GROUPS[i]) == 2) alerting++;
  ring(levelColor(wl));
  small("HOLY-CRAP", CX, 78, C_OR);
  char b[32];
  if (alerting) { snprintf(b, sizeof b, "%d", alerting); txt(b, CX, 170, C_RD, 5); small(alerting == 1 ? "GROUP IN ALERT" : "GROUPS IN ALERT", CX, 240, C_GR); }
  else if (wl == 1) { txt("WATCH", CX, 170, C_OR, 3); small("SOME ABNORMAL SPECIMENS", CX, 230, C_GR); }
  else { txt("OK", CX, 170, C_CY, 5); small("ALL GROUPS NORMAL", CX, 240, C_GR); }
  if (worst >= 0) {
    int idx = 0; for (int i = 0; i < NEV; i++) if (EV[i].bad && !strcmp(EV[i].group, GROUPS[worst])) { idx = i; break; }
    snprintf(b, sizeof b, "%s  %s", GROUPS[worst], EV[idx].type);
    txt(b, CX, 300, C_OR, 1);
  }
  int c; float sum = 0; int k = 0; for (int i = 0; i < NG; i++) { float m = meanGrade(GROUPS[i], &c); if (c) { sum += m; k++; } }
  snprintf(b, sizeof b, "MEAN GRADE %.1f", k ? sum / k : 0.0f);
  small(b, CX, 345, C_WH);
  small("DEMO DATA", CX, 385, C_GR);
  dots();
}
static void pageGroups() {
  small("GROUPS", CX, 62, C_OR);
  for (int i = 0; i < NG; i++) {
    int y = 112 + i * 49; int c; float m = meanGrade(GROUPS[i], &c); int l = level(GROUPS[i]);
    M5.Display.fillRect(104, y - 14, 8, 28, levelColor(l));
    txt(GROUPS[i], 128, y, C_WH, 1, middle_left);
    char b[24]; if (c) snprintf(b, sizeof b, "%.1f", m); else snprintf(b, sizeof b, "--");
    txt(b, 345, y, c ? gradeColor((int)(m + .5f)) : C_GR, 1, middle_right);
  }
  small("mean grade, last 15 min", CX, 408, C_GR);
  dots();
}
static void pageAlert() {
  const Ev& e = EV[nthBad(alertIdx)];
  char b[40];
  snprintf(b, sizeof b, "ALERT %d/%d", alertIdx + 1, badCount());
  small(b, CX, 62, C_OR);
  snprintf(b, sizeof b, "%s  %d min ago", e.group, e.mins);
  txt(b, CX, 102, C_WH, 1);
  snprintf(b, sizeof b, "%d", e.grade);
  txt(b, CX, 190, gradeColor(e.grade), 5);
  small("GRADE", CX, 252, C_GR);
  small("SUSPECTED", CX, 292, C_GR);
  txt(e.type, CX, 324, C_WH, 1);
  snprintf(b, sizeof b, "confidence %d%%", e.conf);
  small(b, CX, 362, C_GR);
  small("A ack  A-hold false  B-hold esc", CX, 404, C_OR);
  dots();
}
static void toast(const char* m) {
  strncpy(toastMsg, m, sizeof toastMsg - 1); toastMsg[sizeof toastMsg - 1] = 0;
  M5.Display.fillRoundRect(CX - 150, CY - 40, 300, 80, 10, C_DK);
  M5.Display.drawRoundRect(CX - 150, CY - 40, 300, 80, 10, C_OR);
  txt(toastMsg, CX, CY - 8, C_OR, 1);
  small("demo only, nothing sent", CX, CY + 22, C_GR);
  toastUntil = millis() + 1500;
}
static void render() {
  M5.Display.fillScreen(C_DK);
  if (page == 0) pageHome(); else if (page == 1) pageGroups(); else pageAlert();
  dirty = false; arcShown = false;
}
static void go(int p) { page = (p + 3) % 3; dirty = true; }

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);
  auto& d = M5.Display;
  d.setRotation(0);
  d.setBrightness(190);
  C_DK = d.color565(0, 0, 0);
  C_OR = d.color565(255, 106, 26);
  C_CY = d.color565(42, 183, 201);
  C_RD = d.color565(255, 59, 48);
  C_GR = d.color565(139, 139, 147);
  C_WH = d.color565(233, 231, 228);
  Serial.printf("console ready, %d events\n", NEV);
}

void loop() {
  M5.update();
  uint32_t now = millis();
  if (toastUntil && now > toastUntil) { toastUntil = 0; dirty = true; }
  if (M5.BtnB.wasClicked() && !toastUntil) go(page + 1);
  if (M5.BtnA.wasClicked() && !toastUntil) { if (page == 2) toast("ACKNOWLEDGED"); else go(2); }
  if (M5.BtnA.wasHold() && page == 2 && !toastUntil) toast("FALSE ALARM");

  // hold B on the alert page to escalate, with a progress ring
  if (M5.BtnB.wasPressed()) { bStart = now; bFired = false; }
  if (page == 2 && M5.BtnB.isPressed() && !bFired && !toastUntil) {
    uint32_t el = now - bStart;
    if (el > 400) {
      float p = (el - 400) / 1100.0f; if (p > 1) p = 1;
      M5.Display.fillArc(CX, CY, 214, 224, 270, fmodf(270 + p * 359.0f, 360.0f), C_RD);
      arcShown = true;
    }
    if (el >= 1500) { bFired = true; toast("ESCALATED"); }
  }
  if (M5.BtnB.wasReleased() && arcShown && !toastUntil) dirty = true;

  // touch swipe and tap
  auto t = M5.Touch.getDetail();
  if (t.wasPressed()) { tx0 = t.x; ty0 = t.y; tlx = t.x; tly = t.y; }
  if (t.isPressed()) { tlx = t.x; tly = t.y; }
  if (t.wasReleased() && !toastUntil) {
    int dx = tlx - tx0, dy = tly - ty0;
    if (abs(dx) > 70 && abs(dx) > abs(dy)) go(page + (dx < 0 ? 1 : -1));
    else if (abs(dx) < 20 && abs(dy) < 20 && page == 2) { alertIdx = (alertIdx + 1) % badCount(); dirty = true; }
  }
  if (dirty && !toastUntil) render();
  delay(10);
}

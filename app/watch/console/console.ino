// StopWatch console with filler data. Same look as the web and phone apps: black, iOS grey cards,
// system green, yellow and red, smooth text. No Wi-Fi yet.
//
// Screens
//   ACTIVE  splash on boot and on every wake
//   LIST    health board, pens ranked by average grade
//   GROUP   photo, grade ring and short facts for the opened pen
//   MENU    acknowledge or false alarm for the shown specimen
//
// Buttons
//   LIST   A click = move highlight down      B click = open the highlighted pen
//   GROUP  A click = next specimen            B click = back to the list
//          A hold  = open the action menu
//          B hold (about 1.5 s) = call the vet for the pen, red alarm screen
//   MENU   A click = next option              B click = choose
//   Any button or touch wakes the screen. The wake press does nothing else.
//   Touch: tap a row in LIST to open it, tap in GROUP for the next specimen.
//
// No on-screen instructions on purpose. The screen only shows information.
// Photos are placeholders from specimens.h, made by app/tools/make_watch_images.py.
#include <M5Unified.h>
#include "specimens.h"

struct Ev { const char* group; const char* type; uint8_t grade; uint8_t conf; uint8_t mins; bool bad; };
static const Ev EV[] = {
  {"B2", "Coccidiosis", 2, 81, 2,  true },
  {"B2", "Coccidiosis", 3, 70, 6,  true },
  {"A1", "Healthy",     9, 93, 9,  false},
  {"B2", "Coccidiosis", 3, 66, 11, true },
  {"C1", "Salmonella",  4, 60, 14, true },
  {"A2", "Healthy",     8, 88, 21, false},
  {"B1", "Newcastle",   3, 52, 33, true },
  {"C2", "Healthy",     10, 96, 47, false},
  {"A1", "Healthy",     8, 90, 62, false},
};
static const int NEV = sizeof(EV) / sizeof(EV[0]);
static const char* IDS[] = {"A1", "A2", "B1", "B2", "C1", "C2"};
static const char* NAMES[] = {"Pen A1", "Pen A2", "Pen B1", "Pen B2", "Cage row C1", "Cage row C2"};
static const int GN[] = {24, 24, 18, 18, 12, 12};
static const int NG = 6;
static const char* MENU[] = {"Acknowledge", "False alarm", "Cancel"};
static const int NMENU = 3;

enum Scr { LIST, GROUP, MENUSCR };
static const uint32_t SLEEP_MS = 20000;
static const uint32_t ESC_MS = 1500;
static const uint32_t SPLASH_MS = 1400;

// Palette, matching the apps. Green healthy, yellow needs a look, red urgent.
static uint16_t C_BLK, C_CARD, C_CARD2, C_SEP, C_TXT, C_SEC, C_TER, C_GOOD, C_WARN, C_BAD;
static const int CX = 233, CY = 233;
static Scr scr = LIST;
static int sel = 0, grp = 0, evIdx = 0, menuSel = 0;
static bool dirty = true, asleep = false, swallow = false, arcShown = false, bFired = false;
static uint32_t lastInput = 0, toastUntil = 0, bStart = 0, splashUntil = 0;
static int tx0, ty0, tlx, tly;
static int ge[16], gcount = 0;      // events of the open pen, newest first
static int order[6];                // pens ranked healthiest first

// ----- data helpers, same rules as the web app -----
static int abnormal15(int gi) { int n = 0; for (int i = 0; i < NEV; i++) if (EV[i].mins <= 15 && EV[i].bad && !strcmp(EV[i].group, IDS[gi])) n++; return n; }
// Average grade over the last hour. Falls back to every specimen if the hour is empty.
static float meanGrade(int gi, bool* any) {
  int n = 0, sum = 0, nAll = 0, sumAll = 0;
  for (int i = 0; i < NEV; i++) {
    if (strcmp(EV[i].group, IDS[gi])) continue;
    nAll++; sumAll += EV[i].grade;
    if (EV[i].mins <= 60) { n++; sum += EV[i].grade; }
  }
  *any = nAll > 0;
  if (n) return (float)sum / n;
  return nAll ? (float)sumAll / nAll : -1;
}
// 0 healthy, 1 needs a look, 2 urgent
static int level(int gi) {
  int bad = abnormal15(gi); bool any; float m = meanGrade(gi, &any);
  return bad >= 3 ? 2 : (bad >= 1 || (any && m < 5)) ? 1 : 0;
}
static uint16_t levelColor(int l) { return l == 2 ? C_BAD : l == 1 ? C_WARN : C_GOOD; }
static uint16_t gradeColor(int g) { return g >= 8 ? C_GOOD : g >= 5 ? C_WARN : C_BAD; }
static void groupStats(int gi, int* n, int* bad) {
  *n = 0; *bad = 0;
  for (int i = 0; i < NEV; i++) if (!strcmp(EV[i].group, IDS[gi])) { (*n)++; if (EV[i].bad) (*bad)++; }
}
static void rankGroups() {
  float m[6]; bool any;
  for (int i = 0; i < NG; i++) { m[i] = meanGrade(i, &any); if (!any) m[i] = -1; order[i] = i; }
  for (int i = 1; i < NG; i++) {
    int k = order[i]; int j = i - 1;
    while (j >= 0 && m[order[j]] < m[k]) { order[j + 1] = order[j]; j--; }
    order[j + 1] = k;
  }
}
static void loadGroup(int gi) {
  gcount = 0;
  for (int i = 0; i < NEV && gcount < 16; i++) if (!strcmp(EV[i].group, IDS[gi])) ge[gcount++] = i;
  evIdx = 0;
}
static int needAttention() { int n = 0; for (int i = 0; i < NG; i++) if (level(i) > 0) n++; return n; }

// ----- drawing helpers -----
static void text(const char* s, int x, int y, uint16_t col, const lgfx::IFont* f, textdatum_t d = middle_center) {
  M5.Display.setFont(f);
  M5.Display.setTextSize(1);
  M5.Display.setTextDatum(d);
  M5.Display.setTextColor(col);
  M5.Display.drawString(s, x, y);
}
static void card(int x, int y, int w, int h, int r, uint16_t col) { M5.Display.fillSmoothRoundRect(x, y, w, h, r, col); }
static void photo(const char* type, int x, int y) {
  const uint8_t* d = IMG_HEALTHY; uint32_t n = IMG_HEALTHY_LEN;
  if (!strcmp(type, "Coccidiosis")) { d = IMG_COCCIDIOSIS; n = IMG_COCCIDIOSIS_LEN; }
  else if (!strcmp(type, "Salmonella")) { d = IMG_SALMONELLA; n = IMG_SALMONELLA_LEN; }
  else if (!strcmp(type, "Newcastle")) { d = IMG_NCD; n = IMG_NCD_LEN; }
  M5.Display.drawJpg(d, n, x, y);
}
// Thin ring that fills clockwise from the top in proportion to the grade out of 10.
static void ringGauge(int cx, int cy, int grade) {
  auto& d = M5.Display;
  d.fillArc(cx, cy, 36, 40, 0, 360, C_SEP);
  uint16_t col = gradeColor(grade);
  if (grade >= 10) d.fillArc(cx, cy, 36, 40, 0, 360, col);
  else d.fillArc(cx, cy, 36, 40, 270, fmodf(270 + grade * 36.0f, 360.0f), col);
  char b[8]; snprintf(b, sizeof b, "%d", grade);
  text(b, cx, cy, C_TXT, &fonts::DejaVu24);
}

// ----- screens -----
static void pageActive() {
  M5.Display.fillScreen(C_BLK);
  M5.Display.fillSmoothCircle(CX, 178, 7, C_GOOD);
  text("Active", CX, 238, C_TXT, &fonts::DejaVu40);
  char b[40]; int a = needAttention();
  if (a) snprintf(b, sizeof b, "%d pens need attention", a); else snprintf(b, sizeof b, "All pens look calm");
  text(b, CX, 300, C_SEC, &fonts::DejaVu18);
  text("Pi 01 online", CX, 334, C_TER, &fonts::DejaVu12);
}
// Rows are 44 px tall and share one card. The selected row gets a lighter pill.
static const int ROW_TOP = 94, ROW_H = 44;
static void pageList() {
  rankGroups();
  M5.Display.fillScreen(C_BLK);
  text("Health board", CX, 60, C_SEC, &fonts::DejaVu18);
  card(62, 88, 342, 276, 26, C_CARD);
  for (int r = 0; r < NG; r++) {
    int gi = order[r], y0 = ROW_TOP + r * ROW_H, yc = y0 + ROW_H / 2;
    bool on = (r == sel);
    if (on) card(70, y0 + 2, 326, ROW_H - 4, 14, C_CARD2);
    else if (r > 0 && r - 1 != sel) M5.Display.drawFastHLine(90, y0, 290, C_SEP);
    bool any; float m = meanGrade(gi, &any);
    char b[16];
    snprintf(b, sizeof b, "%d", r + 1);
    text(b, 94, yc, C_TER, &fonts::DejaVu18);
    text(NAMES[gi], 122, yc, C_TXT, &fonts::DejaVu18, middle_left);
    if (any) snprintf(b, sizeof b, "%.1f", m); else snprintf(b, sizeof b, "n/a");
    text(b, 382, yc, any ? levelColor(level(gi)) : C_TER, &fonts::DejaVu18, middle_right);
  }
  text("Average grade, last hour", CX, 392, C_TER, &fonts::DejaVu12);
}
static void pageGroup() {
  const Ev& e = EV[ge[evIdx]];
  int n, bad; groupStats(grp, &n, &bad);
  char b[48];
  M5.Display.fillScreen(C_BLK);
  text(NAMES[grp], CX, 46, C_TXT, &fonts::DejaVu24);
  snprintf(b, sizeof b, "%d birds", GN[grp]);
  text(b, CX, 74, C_TER, &fonts::DejaVu12);
  card(113, 88, 240, 171, 26, C_CARD);
  photo(e.type, 143, 106);
  card(84, 270, 298, 118, 30, C_CARD);
  ringGauge(142, 329, e.grade);
  text(e.bad ? "Suspected" : "Classified as", 202, 296, C_TER, &fonts::DejaVu12, middle_left);
  text(e.type, 202, 320, e.bad ? C_TXT : C_GOOD, &fonts::DejaVu18, middle_left);
  snprintf(b, sizeof b, "%d%% confident", e.conf);
  text(b, 202, 346, C_SEC, &fonts::DejaVu12, middle_left);
  if (bad) snprintf(b, sizeof b, "%d of %d abnormal", bad, n); else snprintf(b, sizeof b, "All normal");
  text(b, 202, 366, bad ? C_BAD : C_TER, &fonts::DejaVu12, middle_left);
  snprintf(b, sizeof b, "%d of %d", evIdx + 1, gcount);
  text(b, CX, 410, C_TER, &fonts::DejaVu12);
}
static void pageMenu() {
  M5.Display.fillScreen(C_BLK);
  text(NAMES[grp], CX, 76, C_SEC, &fonts::DejaVu18);
  for (int i = 0; i < NMENU; i++) {
    int y = 160 + i * 80; bool on = (i == menuSel);
    card(83, y - 32, 300, 64, 32, on ? C_CARD2 : C_CARD);
    text(MENU[i], CX, y, on ? C_TXT : C_SEC, &fonts::DejaVu18);
  }
}
static void toast(const char* m, const char* sub = "Demo only, nothing sent") {
  card(CX - 150, CY - 50, 300, 100, 34, C_CARD2);
  text(m, CX, CY - 12, C_TXT, &fonts::DejaVu18);
  text(sub, CX, CY + 24, C_TER, &fonts::DejaVu12);
  toastUntil = millis() + 1500;
}
// Red flashes, then a final screen that says what happened.
static void alarmScreen() {
  M5.Power.setVibration(255);
  for (int i = 0; i < 4; i++) {
    uint16_t bg = (i % 2 == 0) ? C_BAD : C_BLK, fg = (i % 2 == 0) ? C_BLK : C_BAD;
    M5.Display.fillScreen(bg);
    text("Terminated", CX, CY, fg, &fonts::DejaVu40);
    delay(220);
  }
  M5.Power.setVibration(0);
  M5.Display.fillScreen(C_BLK);
  M5.Display.fillArc(CX, CY, 212, 224, 0, 360, C_BAD);
  text("Vet called", CX, 212, C_TXT, &fonts::DejaVu40);
  text(NAMES[grp], CX, 268, C_SEC, &fonts::DejaVu24);
  text("Demo only, no call was made", CX, 340, C_TER, &fonts::DejaVu12);
  toastUntil = millis() + 3500;
}
static void render() {
  if (splashUntil) pageActive();
  else if (scr == LIST) pageList();
  else if (scr == GROUP) pageGroup();
  else pageMenu();
  dirty = false; arcShown = false;
}
static void sleepNow() { asleep = true; M5.Display.setBrightness(0); }
static void wake() { asleep = false; swallow = true; M5.Display.setBrightness(190); splashUntil = millis() + SPLASH_MS; dirty = true; }
static void openGroup(int gi) { grp = gi; loadGroup(gi); scr = GROUP; dirty = true; }
// toast, then fall back to the pen screen
static void done(const char* m) { toast(m); scr = GROUP; }

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);
  auto& d = M5.Display;
  d.setRotation(0);
  d.setBrightness(190);
  C_BLK = d.color565(0, 0, 0);
  C_CARD = d.color565(28, 28, 30);
  C_CARD2 = d.color565(52, 52, 56);
  C_SEP = d.color565(58, 58, 62);
  C_TXT = d.color565(255, 255, 255);
  C_SEC = d.color565(172, 172, 180);
  C_TER = d.color565(112, 112, 118);
  C_GOOD = d.color565(48, 209, 88);
  C_WARN = d.color565(255, 214, 10);
  C_BAD = d.color565(255, 69, 58);
  lastInput = millis();
  splashUntil = millis() + SPLASH_MS;
  Serial.printf("console ready, %d events\n", NEV);
}

void loop() {
  M5.update();
  uint32_t now = millis();
  auto t = M5.Touch.getDetail();
  bool pressed = M5.BtnA.isPressed() || M5.BtnB.isPressed() || t.isPressed();
  bool anyDown = M5.BtnA.wasPressed() || M5.BtnB.wasPressed() || t.wasPressed();
  if (anyDown || pressed) lastInput = now;

  if (asleep) {                              // first press only turns the screen on
    if (anyDown) wake();
    delay(10); return;
  }
  if (splashUntil) {                         // Active splash after boot or wake
    if (dirty) render();
    if (now > splashUntil) { splashUntil = 0; dirty = true; swallow = true; }
    delay(10); return;
  }
  if (swallow) {                             // ignore the rest of the waking press
    if (!pressed) swallow = false;
    delay(10); return;
  }
  if (now - lastInput > SLEEP_MS) { sleepNow(); return; }
  if (toastUntil) {
    if (now > toastUntil) { toastUntil = 0; dirty = true; }
    delay(10); return;
  }

  if (scr == LIST) {
    if (M5.BtnA.wasClicked()) { sel = (sel + 1) % NG; dirty = true; }
    if (M5.BtnB.wasClicked()) openGroup(order[sel]);
    if (t.wasPressed()) { tx0 = t.x; ty0 = t.y; tlx = t.x; tly = t.y; }
    if (t.isPressed()) { tlx = t.x; tly = t.y; }
    if (t.wasReleased() && abs(tlx - tx0) < 25 && abs(tly - ty0) < 25 && tly >= ROW_TOP) {
      int r = (tly - ROW_TOP) / ROW_H;
      if (r >= 0 && r < NG) { sel = r; openGroup(order[r]); }
    }
  } else if (scr == GROUP) {
    if (M5.BtnA.wasClicked()) { evIdx = (evIdx + 1) % gcount; dirty = true; }
    if (M5.BtnA.wasHold()) { menuSel = 0; scr = MENUSCR; dirty = true; }
    if (M5.BtnB.wasClicked()) { scr = LIST; dirty = true; }
    // hold B to call the vet for this pen, with a progress ring
    if (M5.BtnB.wasPressed()) { bStart = now; bFired = false; }
    if (M5.BtnB.isPressed() && !bFired) {
      uint32_t el = now - bStart;
      if (el > 400) {
        float p = (el - 400) / (float)(ESC_MS - 400); if (p > 1) p = 1;
        M5.Display.fillArc(CX, CY, 216, 224, 270, fmodf(270 + p * 359.0f, 360.0f), C_BAD);
        arcShown = true;
      }
      if (el >= ESC_MS) { bFired = true; alarmScreen(); scr = LIST; sel = 0; }
    }
    if (M5.BtnB.wasReleased() && arcShown && !bFired) dirty = true;
    if (t.wasPressed()) { tx0 = t.x; ty0 = t.y; tlx = t.x; tly = t.y; }
    if (t.isPressed()) { tlx = t.x; tly = t.y; }
    if (t.wasReleased() && abs(tlx - tx0) < 25 && abs(tly - ty0) < 25) { evIdx = (evIdx + 1) % gcount; dirty = true; }
  } else {
    if (M5.BtnA.wasClicked()) { menuSel = (menuSel + 1) % NMENU; dirty = true; }
    if (M5.BtnB.wasClicked()) {
      if (menuSel == 0) done("Acknowledged");
      else if (menuSel == 1) done("Marked false alarm");
      else { scr = GROUP; dirty = true; }
    }
  }
  if (dirty) render();
  delay(10);
}

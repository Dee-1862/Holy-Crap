// StopWatch console with filler data, liquid glass look. No Wi-Fi yet.
//
// Screens
//   ACTIVE  splash on boot and on every wake
//   LIST    health leaderboard, groups ranked by mean grade
//   GROUP   photo, grade ring and stats for the opened group
//   MENU    acknowledge or false alarm for the shown specimen
//
// Buttons
//   LIST   A click = move highlight down      B click = open the highlighted group
//   GROUP  A click = next specimen            B click = back to the list
//          A hold  = open the action menu
//          B hold (about 1.5 s) = call the vet for the group, red alarm screen
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
  {"B2", "COCCIDIOSIS", 2, 81, 2,  true },
  {"B2", "COCCIDIOSIS", 3, 70, 6,  true },
  {"A1", "HEALTHY",     9, 93, 9,  false},
  {"B2", "COCCIDIOSIS", 3, 66, 11, true },
  {"C1", "SALMONELLA",  4, 60, 14, true },
  {"A2", "HEALTHY",     8, 88, 21, false},
  {"B1", "NEWCASTLE",   3, 52, 33, true },
  {"C2", "HEALTHY",     10, 96, 47, false},
  {"A1", "HEALTHY",     8, 90, 62, false},
};
static const int NEV = sizeof(EV) / sizeof(EV[0]);
static const char* GROUPS[] = {"A1", "A2", "B1", "B2", "C1", "C2"};
static const int GN[] = {24, 24, 18, 18, 12, 12};
static const int NG = 6;
static const char* MENU[] = {"ACKNOWLEDGE", "FALSE ALARM", "CANCEL"};
static const int NMENU = 3;

enum Scr { LIST, GROUP, MENUSCR };
static const uint32_t SLEEP_MS = 20000;
static const uint32_t ESC_MS = 1500;
static const uint32_t SPLASH_MS = 1400;

// Liquid glass palette. Green healthy, yellow normal but watch, red critical.
static uint16_t C_BG1, C_BG2, C_CARD, C_CARD2, C_EDGE, C_GLOSS, C_TXT, C_MUT, C_TRK, C_GLOW, C_ICE;
static uint16_t C_GOOD, C_WARN, C_BAD, C_BLK;
static const int CX = 233, CY = 233;
static Scr scr = LIST;
static int sel = 0, grp = 0, evIdx = 0, menuSel = 0;
static bool dirty = true, asleep = false, swallow = false, arcShown = false, bFired = false;
static uint32_t lastInput = 0, toastUntil = 0, bStart = 0, splashUntil = 0;
static int tx0, ty0, tlx, tly;
static int ge[16], gcount = 0;      // events of the open group, newest first
static int order[6];                // group indexes ranked healthiest first

// ----- data helpers -----
static int badInGroup(int gi) { int n = 0; for (int i = 0; i < NEV; i++) if (EV[i].mins <= 15 && EV[i].bad && !strcmp(EV[i].group, GROUPS[gi])) n++; return n; }
static int level(int gi) { int b = badInGroup(gi); return b >= 3 ? 2 : b >= 1 ? 1 : 0; }
static void groupStats(int gi, int* n, int* bad) {
  *n = 0; *bad = 0;
  for (int i = 0; i < NEV; i++) if (!strcmp(EV[i].group, GROUPS[gi])) { (*n)++; if (EV[i].bad) (*bad)++; }
}
static float recentMean(int gi, int* n) {
  int sum = 0; *n = 0;
  for (int i = 0; i < NEV; i++) if (EV[i].mins <= 15 && !strcmp(EV[i].group, GROUPS[gi])) { (*n)++; sum += EV[i].grade; }
  return *n ? (float)sum / *n : -1;
}
// Rank by mean grade of the last 15 minutes, highest first. Groups with no data go last.
static void rankGroups() {
  float m[6]; int n;
  for (int i = 0; i < NG; i++) { m[i] = recentMean(i, &n); if (!n) m[i] = -1; order[i] = i; }
  for (int i = 1; i < NG; i++) {
    int k = order[i]; int j = i - 1;
    while (j >= 0 && m[order[j]] < m[k]) { order[j + 1] = order[j]; j--; }
    order[j + 1] = k;
  }
}
static void loadGroup(int gi) {
  gcount = 0;
  for (int i = 0; i < NEV && gcount < 16; i++) if (!strcmp(EV[i].group, GROUPS[gi])) ge[gcount++] = i;
  evIdx = 0;
}
static uint16_t gradeColor(int g) { return g >= 8 ? C_GOOD : g >= 5 ? C_WARN : C_BAD; }
static int alertingGroups() { int n = 0; for (int i = 0; i < NG; i++) if (level(i) == 2) n++; return n; }

// ----- drawing helpers -----
static void txt(const char* s, int x, int y, uint16_t col, int size, textdatum_t d = middle_center) {
  M5.Display.setFont(&fonts::Font4);
  M5.Display.setTextSize(size);
  M5.Display.setTextDatum(d);
  M5.Display.setTextColor(col);
  M5.Display.drawString(s, x, y);
}
static void small(const char* s, int x, int y, uint16_t col, textdatum_t d = middle_center) {
  M5.Display.setFont(&fonts::Font2);
  M5.Display.setTextSize(1);
  M5.Display.setTextDatum(d);
  M5.Display.setTextColor(col);
  M5.Display.drawString(s, x, y);
}
// Deep blue vertical gradient with a faint glint along the upper left rim.
static void background() {
  auto& d = M5.Display;
  for (int y = 0; y < 466; y++) {
    int t = y * 255 / 465;
    uint8_t r = 6 + (10 - 6) * t / 255, g = 14 + (46 - 14) * t / 255, b = 34 + (84 - 34) * t / 255;
    d.drawFastHLine(0, y, 466, d.color565(r, g, b));
  }
  d.fillArc(CX, CY, 226, 229, 196, 262, C_GLOSS);
  d.fillArc(CX, CY, 226, 229, 20, 40, C_EDGE);
}
// A frosted glass card: edge, tinted body and a bright gloss line along the top.
static void glass(int x, int y, int w, int h, int r, uint16_t body) {
  auto& d = M5.Display;
  d.fillSmoothRoundRect(x, y, w, h, r, C_EDGE);
  d.fillSmoothRoundRect(x + 1, y + 1, w - 2, h - 2, r - 1, body);
  d.drawFastHLine(x + r, y + 2, w - 2 * r, C_GLOSS);
}
static void photo(const char* type, int x, int y) {
  const uint8_t* d = IMG_HEALTHY; uint32_t n = IMG_HEALTHY_LEN;
  if (!strcmp(type, "COCCIDIOSIS")) { d = IMG_COCCIDIOSIS; n = IMG_COCCIDIOSIS_LEN; }
  else if (!strcmp(type, "SALMONELLA")) { d = IMG_SALMONELLA; n = IMG_SALMONELLA_LEN; }
  else if (!strcmp(type, "NEWCASTLE")) { d = IMG_NCD; n = IMG_NCD_LEN; }
  M5.Display.drawJpg(d, n, x, y);
}
// Ring gauge, fills clockwise from the top in proportion to grade out of 10.
static void ringGauge(int cx, int cy, int grade) {
  auto& d = M5.Display;
  d.fillArc(cx, cy, 33, 42, 0, 360, C_TRK);
  uint16_t col = gradeColor(grade);
  if (grade >= 10) d.fillArc(cx, cy, 33, 42, 0, 360, col);
  else d.fillArc(cx, cy, 33, 42, 270, fmodf(270 + grade * 36.0f, 360.0f), col);
  char b[8]; snprintf(b, sizeof b, "%d", grade);
  txt(b, cx, cy, C_TXT, 2);
}

// ----- screens -----
static void pageActive() {
  background();
  glass(86, 168, 294, 130, 40, C_CARD);
  const int ox[] = {-2, 2, 0, 0, -2, 2, -2, 2};
  const int oy[] = {0, 0, -2, 2, -2, -2, 2, 2};
  for (int i = 0; i < 8; i++) txt("ACTIVE", CX + ox[i], 233 + oy[i], C_GLOW, 3);
  txt("ACTIVE", CX, 233, C_ICE, 3);
  M5.Display.fillSmoothCircle(CX - 70, 330, 5, C_GOOD);
  small("PI 01 ONLINE", CX + 8, 330, C_TXT);
  char b[40]; int a = alertingGroups();
  if (a) snprintf(b, sizeof b, "%d GROUPS   %d IN ALERT", NG, a); else snprintf(b, sizeof b, "%d GROUPS   ALL CALM", NG);
  small(b, CX, 362, C_MUT);
}
// Leaderboard rows are 44 px tall and touch each other inside one glass card.
static const int ROW_TOP = 96, ROW_H = 44;
static void pageList() {
  rankGroups();
  background();
  small("HEALTH BOARD", CX, 64, C_ICE);
  glass(62, 90, 342, 272, 26, C_CARD);
  for (int r = 0; r < NG; r++) {
    int gi = order[r], y0 = ROW_TOP + r * ROW_H, yc = y0 + ROW_H / 2;
    bool on = (r == sel);
    if (on) M5.Display.fillRect(64, y0, 338, ROW_H, C_CARD2);
    else if (r > 0) M5.Display.drawFastHLine(78, y0, 310, C_TRK);
    int c; float m = recentMean(gi, &c);
    char b[16];
    snprintf(b, sizeof b, "%d", r + 1);
    txt(b, 92, yc, C_MUT, 1);
    txt(GROUPS[gi], 124, yc, C_TXT, 1, middle_left);
    // health bar between name and grade
    int g = c ? (int)(m + .5f) : 0;
    M5.Display.fillSmoothRoundRect(190, yc - 4, 120, 8, 4, C_TRK);
    if (c) M5.Display.fillSmoothRoundRect(190, yc - 4, max(8, 12 * g), 8, 4, gradeColor(g));
    if (c) snprintf(b, sizeof b, "%.1f", m); else snprintf(b, sizeof b, "NA");
    txt(b, 384, yc, c ? gradeColor(g) : C_MUT, 1, middle_right);
  }
  small("last 15 min, mean grade", CX, 386, C_MUT);
}
static void pageGroup() {
  const Ev& e = EV[ge[evIdx]];
  int n, bad; groupStats(grp, &n, &bad);
  char b[48];
  background();
  snprintf(b, sizeof b, "GROUP %s", GROUPS[grp]);
  txt(b, CX, 50, C_TXT, 1);
  snprintf(b, sizeof b, "%d birds", GN[grp]);
  small(b, CX, 74, C_MUT);
  glass(113, 90, 240, 171, 26, C_CARD);
  photo(e.type, 143, 108);
  glass(84, 272, 298, 118, 30, C_CARD);
  ringGauge(142, 331, e.grade);
  small(e.bad ? "SUSPECTED" : "CLASSIFIED", 202, 298, C_MUT, middle_left);
  txt(e.type, 202, 320, e.bad ? C_TXT : C_GOOD, 1, middle_left);
  snprintf(b, sizeof b, "%d%% confident", e.conf);
  small(b, 202, 346, C_TXT, middle_left);
  snprintf(b, sizeof b, "%d of %d abnormal", bad, n);
  small(b, 202, 366, bad ? C_WARN : C_MUT, middle_left);
  snprintf(b, sizeof b, "%d / %d", evIdx + 1, gcount);
  small(b, CX, 410, C_MUT);
}
static void pageMenu() {
  background();
  char b[40];
  snprintf(b, sizeof b, "GROUP %s", GROUPS[grp]);
  small(b, CX, 74, C_ICE);
  for (int i = 0; i < NMENU; i++) {
    int y = 150 + i * 84; bool on = (i == menuSel);
    glass(83, y - 30, 300, 60, 30, on ? C_CARD2 : C_CARD);
    txt(MENU[i], CX, y, on ? C_TXT : C_MUT, 1);
  }
}
static void toast(const char* m, const char* sub = "demo only, nothing sent") {
  glass(CX - 150, CY - 48, 300, 96, 34, C_CARD2);
  txt(m, CX, CY - 12, C_TXT, 1);
  small(sub, CX, CY + 24, C_MUT);
  toastUntil = millis() + 1500;
}
// Red flashes, then a final screen that says what happened.
static void alarmScreen() {
  M5.Power.setVibration(255);
  for (int i = 0; i < 4; i++) {
    uint16_t bg = (i % 2 == 0) ? C_BAD : C_BLK, fg = (i % 2 == 0) ? C_BLK : C_BAD;
    M5.Display.fillScreen(bg);
    M5.Display.setFont(&fonts::Font4); M5.Display.setTextSize(2);
    M5.Display.setTextDatum(middle_center); M5.Display.setTextColor(fg);
    M5.Display.drawString("TERMINATED", CX, CY);
    delay(220);
  }
  M5.Power.setVibration(0);
  background();
  M5.Display.fillArc(CX, CY, 206, 224, 0, 360, C_BAD);
  glass(96, 130, 274, 200, 40, C_CARD);
  char b[32];
  small("EMERGENCY", CX, 160, C_BAD);
  txt("VET", CX, 212, C_BAD, 2);
  txt("CALLED", CX, 262, C_TXT, 2);
  snprintf(b, sizeof b, "GROUP %s", GROUPS[grp]);
  small(b, CX, 306, C_ICE);
  small("demo only, no call was made", CX, 370, C_MUT);
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
// toast, then fall back to the group screen
static void done(const char* m) { toast(m); scr = GROUP; }

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);
  auto& d = M5.Display;
  d.setRotation(0);
  d.setBrightness(190);
  C_BLK = d.color565(0, 0, 0);
  C_BG1 = d.color565(6, 14, 34);
  C_BG2 = d.color565(10, 46, 84);
  C_CARD = d.color565(20, 44, 80);
  C_CARD2 = d.color565(36, 74, 122);
  C_EDGE = d.color565(86, 138, 196);
  C_GLOSS = d.color565(150, 200, 240);
  C_TXT = d.color565(236, 244, 250);
  C_MUT = d.color565(138, 166, 192);
  C_TRK = d.color565(38, 66, 104);
  C_GLOW = d.color565(40, 116, 176);
  C_ICE = d.color565(190, 236, 255);
  C_GOOD = d.color565(64, 208, 128);
  C_WARN = d.color565(250, 200, 50);
  C_BAD = d.color565(240, 80, 70);
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
  if (splashUntil) {                         // ACTIVE splash after boot or wake
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
    // hold B to call the vet for this group, with a progress ring
    if (M5.BtnB.wasPressed()) { bStart = now; bFired = false; }
    if (M5.BtnB.isPressed() && !bFired) {
      uint32_t el = now - bStart;
      if (el > 400) {
        float p = (el - 400) / (float)(ESC_MS - 400); if (p > 1) p = 1;
        M5.Display.fillArc(CX, CY, 214, 224, 270, fmodf(270 + p * 359.0f, 360.0f), C_BAD);
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
      if (menuSel == 0) done("ACKNOWLEDGED");
      else if (menuSel == 1) done("FALSE ALARM");
      else { scr = GROUP; dirty = true; }
    }
  }
  if (dirty) render();
  delay(10);
}

// StopWatch console with filler data, driven by the two buttons. No Wi-Fi yet.
//
// Screens
//   LIST   health leaderboard, groups ranked by mean grade, one row highlighted
//   GROUP  stats and a specimen photo for the opened group
//   MENU   acknowledge or false alarm for the shown specimen
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
// The screen sleeps after SLEEP_MS without input. Photos are placeholders from
// specimens.h, made by app/tools/make_watch_images.py.
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

// C_OR is a frost white accent for titles and selection. C_CY is green (healthy).
// C_YL is yellow (normal but watch). C_RD is red (critical, reserved for real alerts).
static uint16_t C_OR, C_CY, C_YL, C_RD, C_GR, C_WH, C_DK;
static const int CX = 233, CY = 233;
static Scr scr = LIST;
static int sel = 0, grp = 0, evIdx = 0, menuSel = 0;
static bool dirty = true, asleep = false, swallow = false, arcShown = false, bFired = false;
static uint32_t lastInput = 0, toastUntil = 0, bStart = 0;
static int tx0, ty0, tlx, tly;
static int ge[16], gcount = 0;      // events of the open group, newest first
static int order[6];                // group indexes ranked healthiest first

// ----- data helpers -----
static int badInGroup(int gi) { int n = 0; for (int i = 0; i < NEV; i++) if (EV[i].mins <= 15 && EV[i].bad && !strcmp(EV[i].group, GROUPS[gi])) n++; return n; }
static int level(int gi) { int b = badInGroup(gi); return b >= 3 ? 2 : b >= 1 ? 1 : 0; }
static void groupStats(int gi, int* n, int* bad, float* mean) {
  int sum = 0; *n = 0; *bad = 0;
  for (int i = 0; i < NEV; i++) if (!strcmp(EV[i].group, GROUPS[gi])) { (*n)++; sum += EV[i].grade; if (EV[i].bad) (*bad)++; }
  *mean = *n ? (float)sum / *n : 0;
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
static uint16_t levelColor(int l) { return l == 2 ? C_RD : l == 1 ? C_YL : C_CY; }
static uint16_t gradeColor(int g) { return g >= 8 ? C_CY : g >= 5 ? C_YL : C_RD; }

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
static void photo(const char* type, int x, int y) {
  const uint8_t* d = IMG_HEALTHY; uint32_t n = IMG_HEALTHY_LEN;
  if (!strcmp(type, "COCCIDIOSIS")) { d = IMG_COCCIDIOSIS; n = IMG_COCCIDIOSIS_LEN; }
  else if (!strcmp(type, "SALMONELLA")) { d = IMG_SALMONELLA; n = IMG_SALMONELLA_LEN; }
  else if (!strcmp(type, "NEWCASTLE")) { d = IMG_NCD; n = IMG_NCD_LEN; }
  M5.Display.drawJpg(d, n, x, y);
  M5.Display.drawRect(x - 1, y - 1, 182, 137, C_GR);
}

// Leaderboard rows are 44 px tall, touch each other and span x 52 to 414.
static const int ROW_TOP = 96, ROW_H = 44, ROW_X = 52, ROW_W = 362;
static void pageList() {
  rankGroups();
  small("HEALTH BOARD", CX, 54, C_OR);
  small("RANK", 92, 80, C_GR, middle_center);
  small("GROUP", 168, 80, C_GR, middle_left);
  small("GRADE", 398, 80, C_GR, middle_right);
  uint16_t band0 = M5.Display.color565(15, 15, 17), band1 = M5.Display.color565(24, 24, 28), hot = M5.Display.color565(36, 58, 64);
  for (int r = 0; r < NG; r++) {
    int gi = order[r], y0 = ROW_TOP + r * ROW_H, yc = y0 + ROW_H / 2;
    bool on = (r == sel);
    uint16_t bg = on ? hot : (r % 2 ? band1 : band0);
    M5.Display.fillRect(ROW_X, y0, ROW_W, ROW_H, bg);
    int c; float m = recentMean(gi, &c);
    uint16_t fg = on ? C_OR : C_WH;
    M5.Display.setFont(&fonts::Font4); M5.Display.setTextSize(1);
    M5.Display.setTextDatum(middle_center); M5.Display.setTextColor(on ? C_OR : C_GR, bg);
    char b[16]; snprintf(b, sizeof b, "%d", r + 1);
    M5.Display.drawString(b, 92, yc);
    M5.Display.setTextDatum(middle_left); M5.Display.setTextColor(fg, bg);
    M5.Display.drawString(GROUPS[gi], 168, yc);
    if (c) snprintf(b, sizeof b, "%.1f", m); else snprintf(b, sizeof b, "NA");
    M5.Display.setTextDatum(middle_right);
    M5.Display.setTextColor(c ? gradeColor((int)(m + .5f)) : C_GR, bg);
    M5.Display.drawString(b, 398, yc);
  }
  small("A down   B open", CX, 394, C_GR);
}
static void pageGroup() {
  const Ev& e = EV[ge[evIdx]];
  int n, bad; float mean; groupStats(grp, &n, &bad, &mean);
  char b[48];
  snprintf(b, sizeof b, "GROUP %s   N=%d", GROUPS[grp], GN[grp]);
  small(b, CX, 56, C_OR);
  photo(e.type, 143, 76);
  small(e.bad ? "SUSPECTED" : "CLASSIFIED", CX, 230, C_GR);
  txt(e.type, CX, 252, e.bad ? C_WH : C_CY, 1);
  small("GRADE", 165, 284, C_GR);
  snprintf(b, sizeof b, "%d", e.grade);
  txt(b, 165, 320, gradeColor(e.grade), 2);
  snprintf(b, sizeof b, "conf %d%%", e.conf);
  small(b, 305, 306, C_WH);
  snprintf(b, sizeof b, "%d min ago", e.mins);
  small(b, 305, 328, C_GR);
  snprintf(b, sizeof b, "%d events  %d abnormal  mean %.1f", n, bad, mean);
  small(b, CX, 362, C_GR);
  snprintf(b, sizeof b, "SPECIMEN %d/%d", evIdx + 1, gcount);
  small(b, CX, 382, C_WH);
  small("A next   A hold menu", CX, 402, C_GR);
  small("B back   B hold call vet", CX, 420, C_OR);
}
static void pageMenu() {
  char b[40];
  snprintf(b, sizeof b, "ACTION   %s", GROUPS[grp]);
  small(b, CX, 66, C_OR);
  for (int i = 0; i < NMENU; i++) {
    int y = 150 + i * 80; bool on = (i == menuSel);
    M5.Display.drawRoundRect(78, y - 28, 310, 56, 8, on ? C_OR : C_GR);
    txt(MENU[i], CX, y, on ? C_OR : C_WH, 1);
  }
  small("A next   B choose", CX, 404, C_GR);
}
static void toast(const char* m, const char* sub = "demo only, nothing sent") {
  M5.Display.fillRoundRect(CX - 150, CY - 44, 300, 88, 10, C_DK);
  M5.Display.drawRoundRect(CX - 150, CY - 44, 300, 88, 10, C_OR);
  txt(m, CX, CY - 10, C_OR, 1);
  small(sub, CX, CY + 24, C_GR);
  toastUntil = millis() + 1500;
}
// Full screen red alarm for the vet call. Flashes, then holds a final screen.
static void alarmScreen() {
  M5.Power.setVibration(255);
  for (int i = 0; i < 4; i++) {
    uint16_t bg = (i % 2 == 0) ? C_RD : C_DK, fg = (i % 2 == 0) ? C_DK : C_RD;
    M5.Display.fillScreen(bg);
    M5.Display.setFont(&fonts::Font4); M5.Display.setTextSize(2);
    M5.Display.setTextDatum(middle_center); M5.Display.setTextColor(fg, bg);
    M5.Display.drawString("TERMINATED", CX, CY);
    delay(220);
  }
  M5.Power.setVibration(0);
  M5.Display.fillScreen(C_DK);
  M5.Display.fillArc(CX, CY, 206, 224, 0, 360, C_RD);
  char b[32];
  small("EMERGENCY", CX, 118, C_RD);
  txt("VET", CX, 188, C_RD, 3);
  txt("CALLED", CX, 262, C_WH, 2);
  snprintf(b, sizeof b, "GROUP %s", GROUPS[grp]);
  txt(b, CX, 330, C_OR, 1);
  small("demo only, no call was made", CX, 372, C_GR);
  toastUntil = millis() + 3500;
}
static void render() {
  M5.Display.fillScreen(C_DK);
  if (scr == LIST) pageList(); else if (scr == GROUP) pageGroup(); else pageMenu();
  dirty = false; arcShown = false;
}
static void sleepNow() { asleep = true; M5.Display.setBrightness(0); }
static void wake() { asleep = false; swallow = true; M5.Display.setBrightness(190); dirty = true; }
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
  C_DK = d.color565(0, 0, 0);
  C_OR = d.color565(214, 232, 236);
  C_CY = d.color565(52, 199, 110);
  C_YL = d.color565(240, 190, 40);
  C_RD = d.color565(232, 64, 56);
  C_GR = d.color565(139, 139, 147);
  C_WH = d.color565(233, 231, 228);
  lastInput = millis();
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
        M5.Display.fillArc(CX, CY, 214, 224, 270, fmodf(270 + p * 359.0f, 360.0f), C_RD);
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

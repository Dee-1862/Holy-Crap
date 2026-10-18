// StopWatch console. Same look as the web and phone apps: black, iOS grey cards, system green,
// yellow and red, smooth text. Works on built in demo data, and goes live when secrets.h exists.
//
// Screens
//   ACTIVE    splash on boot and on every wake
//   OVERVIEW  barn health ring, a status strip for all pens and the pen to check first
//   LIST      health board, pens ranked by average grade
//   PEN       pages for the opened pen: for each specimen a photo page and a why page
//             (explainability, in plain words), then one summary page with the five checks
//   MENU      I'll check it, Looks normal, Call the vet, Cancel
//
// Buttons
//   OVERVIEW  A or B click = health board
//   LIST      A click = move down    B click = open the pen    A hold = overview
//   PEN       A click = next page    B click = back to the list    A hold = actions
//             B hold (about 1.5 s) = call the vet for the pen, the alien shows while the ring fills
//   MENU      A click = next option  B click = choose  (Call the vet needs B held)
//   Touch     tap a row in LIST to open it, tap in PEN to flip photo and why
//   Any button or touch wakes the screen. The wake press does nothing else.
//
// No on screen instructions on purpose. The screen only shows information.
// Real phone calls are on hold. A vet request is logged by the console and goes nowhere else
// unless the console has a webhook set.
#include <M5Unified.h>
#include "specimens.h"

#if __has_include("secrets.h")
  #include "secrets.h"
  #define LIVE 1
  #include <WiFi.h>
  #include <HTTPClient.h>
  #include <ArduinoJson.h>
#else
  #define LIVE 0
#endif

// ----- data -----
static const int NPEN = 6;
static const char* PEN_ID[NPEN]   = {"A1", "A2", "B1", "B2", "C1", "C2"};
static const char* PEN_NAME[NPEN] = {"Pen A1", "Pen A2", "Pen B1", "Pen B2", "Cage row C1", "Cage row C2"};
static const int   PEN_BIRDS[NPEN] = {24, 24, 18, 18, 12, 12};
static const char* KIND[4]  = {"Healthy", "Coccidiosis", "Salmonella", "Newcastle"};
static const char* AXES[5]  = {"Color", "Firmness", "White cap", "Blood", "Foam"};
static const char* LOWER[5] = {"color", "firmness", "white cap", "blood or mucus", "foam"};
static const char* WORD[5][3] = {            // normal, a bit off, problem
  {"Normal", "A bit off", "Unusual"}, {"Firm", "Soft", "Watery"}, {"Present", "Thin", "Missing"},
  {"None seen", "Some", "Seen"}, {"None", "Some", "Foamy"},
};
static const char* MENU[]   = {"I'll check it", "Looks normal", "Call the vet", "Cancel"};
static const int NMENU = 4;

struct Spec {
  char id[10]; uint8_t pen; uint8_t k; uint8_t grade; uint8_t conf; uint8_t mins; uint8_t st;  // st 0 new, 1 checking, 2 normal
  uint8_t p[4]; uint8_t sub[5]; uint8_t rx, ry; char why[3][72];
};
static const int MAXSPEC = 24;
static Spec SP[MAXSPEC];
static int NSP = 0;
static bool liveOk = false;            // true while the console answers
static uint32_t lastSync = 0, vetAt = 0;
static int vetPen = -1;                // most recent vet request, from the console

struct Demo { const char* id; const char* pen; uint8_t k, grade, conf, mins; uint8_t p[4]; uint8_t sub[5]; uint8_t rx, ry; const char* why[3]; };
static const Demo DEMO[] = {
  {"E-0412", "B2", 1, 2, 81, 2,  {6, 81, 9, 4},   {2, 3, 4, 1, 8},  42, 55, {"Dark red-brown streaking across the lower third", "Wet, mucus-like outline instead of a firm shape", "White urate cap is thin or missing"}},
  {"E-0411", "B2", 1, 3, 70, 6,  {12, 70, 14, 4}, {3, 4, 5, 2, 8},  55, 48, {"Dark brown with red tint near the center", "Soft edges, moderate moisture", ""}},
  {"E-0410", "A1", 0, 9, 93, 9,  {93, 3, 3, 1},   {9, 9, 9, 10, 10}, 50, 42, {"Uniform brown body", "Firm shape with a distinct white urate cap", "No blood, foam or abnormal color"}},
  {"E-0413", "B2", 1, 3, 66, 11, {10, 66, 18, 6}, {3, 4, 4, 2, 8},  47, 52, {"Dark brown with red streaks", "Loose, watery edge", "Third abnormal specimen from this pen in 15 minutes"}},
  {"E-0409", "C1", 2, 4, 60, 14, {22, 8, 60, 10}, {4, 3, 6, 9, 3},  46, 60, {"Yellowish tint over most of the area", "Foamy texture with small bubbles", "Watery spread beyond the normal footprint"}},
  {"E-0408", "A2", 0, 8, 88, 21, {88, 5, 5, 2},   {8, 8, 9, 10, 10}, 48, 50, {"Brown body, slightly moist", "White cap present", ""}},
  {"E-0407", "B1", 3, 3, 52, 33, {20, 5, 15, 52}, {2, 3, 5, 9, 7},  52, 46, {"Green tint across the specimen", "Watery consistency", "Low confidence, a second look is advised"}},
  {"E-0406", "C2", 0, 10, 96, 47, {96, 2, 1, 1},  {10, 10, 9, 10, 10}, 50, 50, {"Textbook example of a firm brown dropping with a white cap", "", ""}},
  {"E-0405", "A1", 0, 8, 90, 62, {90, 4, 4, 2},   {8, 9, 8, 10, 10}, 44, 52, {"Brown, firm", "White cap slightly smeared", ""}},
};
static int penIndex(const char* id) { for (int i = 0; i < NPEN; i++) if (!strcmp(PEN_ID[i], id)) return i; return -1; }
static void loadDemo() {
  NSP = 0;
  for (const Demo& d : DEMO) {
    Spec& s = SP[NSP++]; memset(&s, 0, sizeof s);
    strlcpy(s.id, d.id, sizeof s.id); s.pen = penIndex(d.pen); s.k = d.k; s.grade = d.grade; s.conf = d.conf; s.mins = d.mins; s.st = 0;
    memcpy(s.p, d.p, 4); memcpy(s.sub, d.sub, 5); s.rx = d.rx; s.ry = d.ry;
    for (int j = 0; j < 3; j++) strlcpy(s.why[j], d.why[j], sizeof s.why[j]);
  }
}

// ----- rules, the same as the console (lib/rules.ts) -----
// Specimens marked normal drop out of every number.
static bool counts(const Spec& s) { return s.st != 2; }
static int abnormal15(int pen) { int n = 0; for (int i = 0; i < NSP; i++) if (SP[i].pen == pen && counts(SP[i]) && SP[i].mins <= 15 && SP[i].k != 0) n++; return n; }
static float meanGrade(int pen, bool* any) {
  int n = 0, sum = 0, nAll = 0, sumAll = 0;
  for (int i = 0; i < NSP; i++) {
    if (SP[i].pen != pen || !counts(SP[i])) continue;
    nAll++; sumAll += SP[i].grade;
    if (SP[i].mins <= 60) { n++; sum += SP[i].grade; }
  }
  *any = nAll > 0;
  if (n) return (float)sum / n;
  return nAll ? (float)sumAll / nAll : -1;
}
static int level(int pen) {                      // 0 healthy, 1 needs a look, 2 urgent
  int bad = abnormal15(pen); bool any; float m = meanGrade(pen, &any);
  return bad >= 3 ? 2 : (bad >= 1 || (any && m < 5)) ? 1 : 0;
}
static int needAttention() { int n = 0; for (int i = 0; i < NPEN; i++) if (level(i) > 0) n++; return n; }
static float barnHealth() {                      // grade out of 100 over the last 15 minutes
  int n = 0, sum = 0, nAll = 0, sumAll = 0;
  for (int i = 0; i < NSP; i++) { if (!counts(SP[i])) continue; nAll++; sumAll += SP[i].grade; if (SP[i].mins <= 15) { n++; sum += SP[i].grade; } }
  if (n) return 10.0f * sum / n;
  return nAll ? 10.0f * sumAll / nAll : 0;
}
static int order[NPEN];
static void rankPens() {
  float m[NPEN]; bool any;
  for (int i = 0; i < NPEN; i++) { m[i] = meanGrade(i, &any); if (!any) m[i] = -1; order[i] = i; }
  for (int i = 1; i < NPEN; i++) { int k = order[i], j = i - 1; while (j >= 0 && m[order[j]] < m[k]) { order[j + 1] = order[j]; j--; } order[j + 1] = k; }
}

// ----- palette, matching the apps -----
static uint16_t C_BLK, C_CARD, C_CARD2, C_SEP, C_TXT, C_SEC, C_TER, C_GOOD, C_WARN, C_BAD, D_GOOD, D_WARN, D_BAD;
static const int CX = 233, CY = 233;
static uint16_t levelColor(int l) { return l == 2 ? C_BAD : l == 1 ? C_WARN : C_GOOD; }
static uint16_t levelDim(int l) { return l == 2 ? D_BAD : l == 1 ? D_WARN : D_GOOD; }
static uint16_t gradeColor(int g) { return g >= 8 ? C_GOOD : g >= 5 ? C_WARN : C_BAD; }

// ----- ui state -----
enum Scr { OVERVIEW, LIST, PEN, MENUSCR };
static const uint32_t SLEEP_MS = 20000, ESC_MS = 1500, SPLASH_MS = 1400;
static Scr scr = OVERVIEW;
static int sel = 0, pen = 0, pg = 0, menuSel = 0, ge[MAXSPEC], gcount = 0;
static bool dirty = true, asleep = false, swallow = false, arcShown = false, bFired = false;
static uint32_t lastInput = 0, toastUntil = 0, bStart = 0, splashUntil = 0;
static int tx0, ty0, tlx, tly;

static void loadPen(int p) { gcount = 0; for (int i = 0; i < NSP && gcount < MAXSPEC; i++) if (SP[i].pen == p) ge[gcount++] = i; }
static int pages() { return 2 * gcount + 1; }            // photo and why for each specimen, then the summary
static bool summaryPage() { return pg >= 2 * gcount; }
static Spec& curSpec() { return SP[ge[min(pg / 2, gcount - 1)]]; }

// ----- network -----
#if LIVE
static bool http(const char* method, const String& path, const char* body, JsonDocument& out) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient h; h.setTimeout(2500);
  if (!h.begin(String(API_BASE) + path)) return false;
  if (body) h.addHeader("Content-Type", "application/json");
  int code = !strcmp(method, "POST") ? h.POST(body ? body : "{}") : h.GET();
  bool ok = code == 200 && !deserializeJson(out, h.getString());
  h.end();
  return ok;
}
static void syncNow() {
  JsonDocument doc;
  liveOk = http("GET", "/api/watch", nullptr, doc);
  lastSync = millis();
  if (!liveOk) return;
  NSP = 0;
  for (JsonObject o : doc["specs"].as<JsonArray>()) {
    if (NSP >= MAXSPEC) break;
    Spec& s = SP[NSP]; memset(&s, 0, sizeof s);
    int pi = penIndex(o["pen"] | ""); if (pi < 0) continue;
    strlcpy(s.id, o["id"] | "", sizeof s.id); s.pen = pi;
    String k = o["k"] | "healthy"; s.k = k == "coccidiosis" ? 1 : k == "salmonella" ? 2 : k == "ncd" ? 3 : 0;
    s.grade = o["grade"] | 0; s.conf = o["conf"] | 0; s.mins = o["mins"] | 0; s.st = o["st"] | 0;
    for (int j = 0; j < 4; j++) s.p[j] = o["p"][j] | 0;
    for (int j = 0; j < 5; j++) s.sub[j] = o["sub"][j] | 0;
    s.rx = o["rg"][0] | 50; s.ry = o["rg"][1] | 50;
    for (int j = 0; j < 3; j++) strlcpy(s.why[j], o["why"][j] | "", sizeof s.why[j]);
    NSP++;
  }
  vetPen = doc["vet"].isNull() ? -1 : penIndex(doc["vet"]["pen"] | "");
  vetAt = doc["vet"]["ago"] | 0;
  if (scr == PEN || scr == MENUSCR) { loadPen(pen); pg = min(pg, pages() - 1); }
  dirty = true;
}
#endif

// ----- drawing helpers -----
static void text(const char* s, int x, int y, uint16_t col, const lgfx::IFont* f, textdatum_t d = middle_center) {
  M5.Display.setFont(f); M5.Display.setTextSize(1); M5.Display.setTextDatum(d); M5.Display.setTextColor(col); M5.Display.drawString(s, x, y);
}
static void card(int x, int y, int w, int h, int r, uint16_t col) { M5.Display.fillSmoothRoundRect(x, y, w, h, r, col); }
static void photo(int k, int x, int y) {
  const uint8_t* d = IMG_HEALTHY; uint32_t n = IMG_HEALTHY_LEN;
  if (k == 1) { d = IMG_COCCIDIOSIS; n = IMG_COCCIDIOSIS_LEN; }
  else if (k == 2) { d = IMG_SALMONELLA; n = IMG_SALMONELLA_LEN; }
  else if (k == 3) { d = IMG_NCD; n = IMG_NCD_LEN; }
  M5.Display.drawJpg(d, n, x, y);
}
// Thin ring, filled clockwise from the top. frac is 0 to 1.
static void ring(int cx, int cy, int r0, int r1, float frac, uint16_t col) {
  auto& d = M5.Display;
  d.fillArc(cx, cy, r0, r1, 0, 360, C_SEP);
  if (frac >= 0.999f) d.fillArc(cx, cy, r0, r1, 0, 360, col);
  else if (frac > 0.005f) d.fillArc(cx, cy, r0, r1, 270, fmodf(270 + frac * 360.0f, 360.0f), col);
}
// Word wrapped text, up to maxLines lines.
static void wrap(const char* s, int x, int y, int maxW, int lineH, int maxLines, uint16_t col) {
  auto& d = M5.Display;
  d.setFont(&fonts::DejaVu12); d.setTextSize(1); d.setTextDatum(top_left); d.setTextColor(col);
  char line[96] = ""; int lines = 0; const char* p = s;
  while (*p && lines < maxLines) {
    const char* e = p; while (*e && *e != ' ') e++;
    char word[40]; int wl = min((int)(e - p), 39); memcpy(word, p, wl); word[wl] = 0;
    char trial[130]; snprintf(trial, sizeof trial, "%s%s%s", line, line[0] ? " " : "", word);
    if (d.textWidth(trial) > maxW && line[0]) { d.drawString(line, x, y + lines * lineH); lines++; line[0] = 0; continue; }
    strlcpy(line, trial, sizeof line);
    p = *e ? e + 1 : e;
  }
  if (line[0] && lines < maxLines) d.drawString(line, x, y + lines * lineH);
}

// ----- screens -----
static void pageActive() {
  M5.Display.fillScreen(C_BLK);
  M5.Display.fillSmoothCircle(CX, 178, 7, C_GOOD);
  text("Active", CX, 238, C_TXT, &fonts::DejaVu40);
  char b[40]; int a = needAttention();
  if (a) snprintf(b, sizeof b, "%d pens need attention", a); else snprintf(b, sizeof b, "All pens look calm");
  text(b, CX, 300, C_SEC, &fonts::DejaVu18);
  text(LIVE ? (liveOk ? "Live" : "Connecting") : "Demo data", CX, 334, C_TER, &fonts::DejaVu12);
}
// Aggregate view: barn health ring, one strip that shows how many pens are healthy, need a look or
// are urgent, and the pen to check first. The full list of pens is on the health board.
static void pageOverview() {
  M5.Display.fillScreen(C_BLK);
  text("Barn", CX, 48, C_SEC, &fonts::DejaVu18);
  float h = barnHealth(); int gi = (int)(h / 10 + 0.5f);
  ring(CX, 142, 54, 60, h / 100.0f, gradeColor(gi));
  char b[32]; snprintf(b, sizeof b, "%d", (int)(h + 0.5f));
  text(b, CX, 138, C_TXT, &fonts::DejaVu40);
  text("out of 100", CX, 172, C_TER, &fonts::DejaVu12);
  text("Barn health", CX, 224, C_SEC, &fonts::DejaVu12);

  int c[3] = {0, 0, 0}; for (int i = 0; i < NPEN; i++) c[level(i)]++;
  const int sw = 280, x0 = CX - sw / 2, sy = 248, gap = 4;
  int segs = (c[0] > 0) + (c[1] > 0) + (c[2] > 0);
  float unit = (sw - gap * max(0, segs - 1)) / (float)NPEN; float x = x0;
  for (int l = 0; l < 3; l++) {
    if (!c[l]) continue;
    int w = (int)(unit * c[l] + 0.5f);
    M5.Display.fillSmoothRoundRect((int)x, sy, w, 10, 5, levelColor(l));
    x += w + gap;
  }
  const char* lab[3] = {"healthy", "need a look", "urgent"};
  for (int l = 0; l < 3; l++) {
    int cxl = 118 + l * 115;
    M5.Display.fillSmoothCircle(cxl - 34, 284, 4, c[l] ? levelColor(l) : C_SEP);
    snprintf(b, sizeof b, "%d %s", c[l], lab[l]);
    text(b, cxl - 24, 284, c[l] ? C_SEC : C_TER, &fonts::DejaVu12, middle_left);
  }

  int worst = -1; float wm = 99;
  for (int i = 0; i < NPEN; i++) {
    bool any; float m = meanGrade(i, &any);
    if (level(i) > 0 && (worst < 0 || level(i) > level(worst) || (level(i) == level(worst) && any && m < wm))) { worst = i; wm = any ? m : 99; }
  }
  if (worst >= 0) {
    text("Check first", CX, 330, C_TER, &fonts::DejaVu12);
    text(PEN_NAME[worst], CX, 358, levelColor(level(worst)), &fonts::DejaVu24);
  } else {
    text("All pens look calm", CX, 346, C_GOOD, &fonts::DejaVu18);
  }
  text(LIVE ? (liveOk ? "Live" : "Offline") : "Demo data", CX, 404, C_TER, &fonts::DejaVu12);
}
static const int ROW_TOP = 94, ROW_H = 44;
static void pageList() {
  rankPens();
  M5.Display.fillScreen(C_BLK);
  text("Health board", CX, 60, C_SEC, &fonts::DejaVu18);
  card(62, 88, 342, 276, 26, C_CARD);
  for (int r = 0; r < NPEN; r++) {
    int gi = order[r], y0 = ROW_TOP + r * ROW_H, yc = y0 + ROW_H / 2; bool on = (r == sel);
    if (on) card(70, y0 + 2, 326, ROW_H - 4, 14, C_CARD2);
    else if (r > 0 && r - 1 != sel) M5.Display.drawFastHLine(90, y0, 290, C_SEP);
    bool any; float m = meanGrade(gi, &any); char b[16];
    snprintf(b, sizeof b, "%d", r + 1); text(b, 94, yc, C_TER, &fonts::DejaVu18);
    text(PEN_NAME[gi], 122, yc, C_TXT, &fonts::DejaVu18, middle_left);
    if (any) snprintf(b, sizeof b, "%.1f", m); else snprintf(b, sizeof b, "n/a");
    text(b, 382, yc, any ? levelColor(level(gi)) : C_TER, &fonts::DejaVu18, middle_right);
  }
  text("Average grade, last hour", CX, 392, C_TER, &fonts::DejaVu12);
}
static void stateTag(const Spec& s, int x, int y) {
  if (s.st == 1) text("Being checked", x, y, C_WARN, &fonts::DejaVu12);
  else if (s.st == 2) text("Marked normal", x, y, C_TER, &fonts::DejaVu12);
}
// Photo page. Numbered markers sit on the photo and match the numbered lines on the why page.
static void pagePhoto() {
  Spec& s = curSpec(); char b[48];
  M5.Display.fillScreen(C_BLK);
  text(PEN_NAME[pen], CX, 46, C_TXT, &fonts::DejaVu24);
  snprintf(b, sizeof b, "%d birds", PEN_BIRDS[pen]); text(b, CX, 74, C_TER, &fonts::DejaVu12);
  card(113, 88, 240, 171, 26, C_CARD);
  photo(s.k, 143, 106);
  const int dx[3] = {-23, 27, -4}, dy[3] = {-14, 5, 27};       // same offsets as the web app, in photo pixels
  for (int i = 0; i < 3; i++) {
    if (!s.why[i][0]) continue;
    int mx = 143 + s.rx * 180 / 100 + dx[i], my = 106 + s.ry * 135 / 100 + dy[i];
    mx = constrain(mx, 143 + 12, 143 + 168); my = constrain(my, 106 + 12, 106 + 123);
    M5.Display.fillSmoothCircle(mx, my, 11, C_CARD2); M5.Display.drawCircle(mx, my, 11, C_TXT);
    snprintf(b, sizeof b, "%d", i + 1); text(b, mx, my, C_TXT, &fonts::DejaVu12);
  }
  card(84, 270, 298, 118, 30, C_CARD);
  ring(142, 329, 36, 40, s.grade / 10.0f, gradeColor(s.grade));
  snprintf(b, sizeof b, "%d", s.grade); text(b, 142, 329, C_TXT, &fonts::DejaVu24);
  text(s.k ? "Suspected" : "Classified as", 202, 296, C_TER, &fonts::DejaVu12, middle_left);
  text(KIND[s.k], 202, 320, s.k ? C_TXT : C_GOOD, &fonts::DejaVu18, middle_left);
  snprintf(b, sizeof b, "%d%% confident", s.conf); text(b, 202, 346, C_SEC, &fonts::DejaVu12, middle_left);
  if (s.st) stateTag(s, 202, 366); else { snprintf(b, sizeof b, "%d min ago", s.mins); text(b, 202, 366, C_TER, &fonts::DejaVu12, middle_left); }
  snprintf(b, sizeof b, "%d of %d", pg / 2 + 1, gcount); text(b, CX, 410, C_TER, &fonts::DejaVu12);
}
// Explainability in plain words: what it most likely is, how sure it is, and what it saw.
static void pageWhy() {
  Spec& s = curSpec(); char b[64];
  M5.Display.fillScreen(C_BLK);
  text("Why this result", CX, 48, C_SEC, &fonts::DejaVu18);
  text(s.k ? "Most likely" : "Looks like", CX, 90, C_TER, &fonts::DejaVu12);
  text(KIND[s.k], CX, 120, s.k ? C_TXT : C_GOOD, &fonts::DejaVu24);
  const char* word = s.conf >= 80 ? "Very sure" : s.conf >= 60 ? "Fairly sure" : "Not sure";
  int dots = s.conf >= 80 ? 3 : s.conf >= 60 ? 2 : 1;
  // Dots and words are centered as one group. The text is measured so the dots never touch it.
  M5.Display.setFont(&fonts::DejaVu18);
  int tw = M5.Display.textWidth(word), total = 3 * 16 + 14 + tw, sx = CX - total / 2;
  for (int i = 0; i < 3; i++) M5.Display.fillSmoothCircle(sx + 6 + i * 16, 158, 5, i < dots ? C_TXT : C_SEP);
  text(word, sx + 3 * 16 + 14, 158, C_TXT, &fonts::DejaVu18, middle_left);
  int second = -1; for (int i = 0; i < 4; i++) if (i != s.k && s.p[i] >= 15 && (second < 0 || s.p[i] > s.p[second])) second = i;
  if (second >= 0) { snprintf(b, sizeof b, "It could also be %s", KIND[second]); text(b, CX, 190, C_SEC, &fonts::DejaVu12); }
  // evidence lines, numbered like the markers on the photo
  int y = 222;
  for (int i = 0; i < 3; i++) {
    if (!s.why[i][0]) continue;
    M5.Display.fillSmoothCircle(94, y + 8, 11, C_CARD2);
    snprintf(b, sizeof b, "%d", i + 1); text(b, 94, y + 8, C_TXT, &fonts::DejaVu12);
    wrap(s.why[i], 116, y, 262, 15, 2, C_TXT);
    y += 52;
  }
  snprintf(b, sizeof b, "%d of %d", pg / 2 + 1, gcount); text(b, CX, 410, C_TER, &fonts::DejaVu12);
}
// Pen summary: the five checks in plain words, averaged over the pen's specimens.
static void pageSummary() {
  M5.Display.fillScreen(C_BLK);
  text(PEN_NAME[pen], CX, 46, C_TXT, &fonts::DejaVu24);
  text("What we checked", CX, 78, C_TER, &fonts::DejaVu12);
  float v[5] = {0}; int n = 0;
  for (int i = 0; i < gcount; i++) { Spec& sp = SP[ge[i]]; if (!counts(sp)) continue; n++; for (int j = 0; j < 5; j++) v[j] += sp.sub[j]; }
  for (int j = 0; j < 5; j++) v[j] = n ? v[j] / n : 0;
  card(70, 98, 326, 240, 26, C_CARD);
  for (int j = 0; j < 5; j++) {
    int y0 = 104 + j * 46, yc = y0 + 23; int lv = !n ? 0 : v[j] >= 8 ? 0 : v[j] >= 5 ? 1 : 2;
    if (j > 0) M5.Display.drawFastHLine(94, y0, 278, C_SEP);
    text(AXES[j], 96, yc, C_TXT, &fonts::DejaVu18, middle_left);
    text(n ? WORD[j][lv] : "n/a", 350, yc, lv ? levelColor(lv == 2 ? 2 : 1) : C_SEC, &fonts::DejaVu18, middle_right);
    M5.Display.fillSmoothCircle(374, yc, 5, n ? levelColor(lv) : C_SEP);
  }
  char b[80];
  int a = -1, c2 = -1;                                         // the two lowest checks that are off
  for (int j = 0; j < 5; j++) if (v[j] < 8) { if (a < 0 || v[j] < v[a]) { c2 = a; a = j; } else if (c2 < 0 || v[j] < v[c2]) c2 = j; }
  if (!n) snprintf(b, sizeof b, "No specimens counted");
  else if (a < 0) snprintf(b, sizeof b, "All five checks look normal");
  else if (c2 < 0) snprintf(b, sizeof b, "Mostly %s is off", LOWER[a]);
  else snprintf(b, sizeof b, "Mostly %s and %s are off", LOWER[a], LOWER[c2]);
  text(b, CX, 366, C_SEC, &fonts::DejaVu12);
  if (vetPen == pen) { snprintf(b, sizeof b, "Vet requested %d min ago", (int)vetAt); text(b, CX, 388, C_GOOD, &fonts::DejaVu12); }
  text("Pen summary", CX, 410, C_TER, &fonts::DejaVu12);
}
static void pageMenu() {
  M5.Display.fillScreen(C_BLK);
  text(PEN_NAME[pen], CX, 64, C_SEC, &fonts::DejaVu18);
  for (int i = 0; i < NMENU; i++) {
    int y = 122 + i * 66; bool on = (i == menuSel);
    card(83, y - 26, 300, 52, 26, on ? C_CARD2 : C_CARD);
    text(MENU[i], CX, y, i == 2 ? (on ? C_BAD : C_SEC) : (on ? C_TXT : C_SEC), &fonts::DejaVu18);
  }
  text("Call the vet needs B held", CX, 408, C_TER, &fonts::DejaVu12);
}
// ----- the alien that shows while the termination ring fills and when it finishes -----
// 20 by 17 pixel art. . empty, # outline and eyes, p body, l light ear tips.
static const char* ALIEN[17] = {
  "...###........###...",
  "...#l####..####l#...",
  "..#####l#..#l#####..",
  "..#pp##p####p##pp#..",
  "###p##pppppppp##p###",
  "#p###pppppppppp###p#",
  "#p##pppppppppppp##p#",
  "#p##pp##pppp##pp##p#",
  "#p##pp##pppp##pp##p#",
  "##pppp##pppp##pppp##",
  ".###pppppppppppp###.",
  "..##pppppppppppp##..",
  "..####pp####pp####..",
  ".....#pp#..#pp#.....",
  "...######..######...",
  "...#p#........#p#...",
  "...###........###..."
};
// cell is the size of one sprite pixel on screen. The sprite is drawn centered on cx, cy.
static void drawAlien(int cx, int cy, int cell) {
  auto& d = M5.Display;
  uint16_t outline = d.color565(2, 2, 2), body = d.color565(124, 89, 171), light = d.color565(150, 115, 195);
  int x0 = cx - 10 * cell, y0 = cy - 17 * cell / 2;
  for (int r = 0; r < 17; r++) {
    for (int c = 0; c < 20; c++) {
      char ch = ALIEN[r][c]; if (ch == '.') continue;
      d.fillRect(x0 + c * cell, y0 + r * cell, cell, cell, ch == '#' ? outline : ch == 'l' ? light : body);
    }
  }
}
// One frame while B is held. The first frame clears the screen, then the alien bobs and the red
// ring grows around the edge. p runs from 0 to 1.
static void holdFrame(float p, uint32_t now) {
  auto& d = M5.Display;
  if (!arcShown) { d.fillScreen(C_BLK); arcShown = true; }
  d.fillSmoothCircle(CX, CY, 96, C_CARD);
  drawAlien(CX, CY + ((now / 170) % 2) * 4 - 2, 7);
  d.fillArc(CX, CY, 216, 224, 270, fmodf(270 + p * 359.0f, 360.0f), C_BAD);
}
// Finish screen for the termination. No flashing. Says plainly what happened.
static void terminatedScreen(const char* line1, const char* line2) {
  auto& d = M5.Display;
  d.fillScreen(C_BLK);
  d.fillArc(CX, CY, 216, 224, 0, 360, C_BAD);
  d.fillSmoothCircle(CX, 150, 78, C_CARD);
  drawAlien(CX, 150, 6);
  text("Terminated", CX, 262, C_TXT, &fonts::DejaVu24);
  text(PEN_NAME[pen], CX, 296, C_SEC, &fonts::DejaVu18);
  text(line1, CX, 338, C_TXT, &fonts::DejaVu18);
  text(line2, CX, 366, C_TER, &fonts::DejaVu12);
}
static void toast(const char* m, const char* sub) {
  card(CX - 150, CY - 50, 300, 100, 34, C_CARD2);
  text(m, CX, CY - 12, C_TXT, &fonts::DejaVu18);
  text(sub, CX, CY + 24, C_TER, &fonts::DejaVu12);
  toastUntil = millis() + 1700;
}
static void render() {
  if (splashUntil) pageActive();
  else if (scr == OVERVIEW) pageOverview();
  else if (scr == LIST) pageList();
  else if (scr == MENUSCR) pageMenu();
  else if (summaryPage()) pageSummary();
  else if (pg % 2 == 0) pagePhoto();
  else pageWhy();
  dirty = false; arcShown = false;
}

// ----- actions, same as the web app buttons -----
static const char* where() {
#if LIVE
  return liveOk ? "Shared with the team" : "Saved on the watch only";
#else
  return "Demo data, saved on the watch only";
#endif
}
static void setState(int specIdx, int st, const char* path) {
  SP[specIdx].st = st;
#if LIVE
  JsonDocument d; liveOk = http("POST", String("/api/specimens/") + SP[specIdx].id + "/" + path, nullptr, d);
#endif
}
static void actCheck() { setState(ge[min(pg / 2, gcount - 1)], 1, "check"); toast("I'll check it", where()); scr = PEN; }
static void actNormal() { setState(ge[min(pg / 2, gcount - 1)], 2, "normal"); toast("Marked normal", "Removed from alerts"); scr = PEN; }
// Vet request. Shows the alien, then says plainly what happened. No phone call is placed.
static void actVet() {
  const char* line1 = "Vet request saved"; const char* line2 = where();
#if LIVE
  JsonDocument d; char body[48]; snprintf(body, sizeof body, "{\"specimenId\":\"%s\"}", summaryPage() ? "" : curSpec().id);
  liveOk = http("POST", String("/api/pens/") + PEN_ID[pen] + "/vet", body, d);
  if (liveOk) {
    if (d["duplicate"] | false) { line1 = "Already requested"; line2 = "In the last minute"; }
    else if (!strcmp(d["call"]["delivered"] | "", "sent")) { line1 = "Vet notified"; line2 = "Message sent"; }
    else if (!strcmp(d["call"]["delivered"] | "", "failed")) { line1 = "Saved, not sent"; line2 = "Check the webhook"; }
    else line2 = "No phone service connected yet";
  }
#else
  line2 = "Demo data, nothing sent";
#endif
  vetPen = pen; vetAt = 0;
  M5.Power.setVibration(255); delay(160); M5.Power.setVibration(0);     // one short buzz, no flashing
  terminatedScreen(line1, line2);
  toastUntil = millis() + 3500;
  scr = LIST; sel = 0;
}

static void sleepNow() { asleep = true; M5.Display.setBrightness(0); }
static void wake() { asleep = false; swallow = true; M5.Display.setBrightness(190); splashUntil = millis() + SPLASH_MS; dirty = true; }
static void openPen(int p) { pen = p; loadPen(p); pg = 0; scr = PEN; dirty = true; }

void setup() {
  auto cfg = M5.config(); M5.begin(cfg); Serial.begin(115200);
  auto& d = M5.Display; d.setRotation(0); d.setBrightness(190);
  C_BLK = d.color565(0, 0, 0); C_CARD = d.color565(28, 28, 30); C_CARD2 = d.color565(52, 52, 56); C_SEP = d.color565(58, 58, 62);
  C_TXT = d.color565(255, 255, 255); C_SEC = d.color565(172, 172, 180); C_TER = d.color565(112, 112, 118);
  C_GOOD = d.color565(48, 209, 88); C_WARN = d.color565(255, 214, 10); C_BAD = d.color565(255, 69, 58);
  D_GOOD = d.color565(14, 52, 24); D_WARN = d.color565(66, 56, 4); D_BAD = d.color565(68, 22, 18);
  loadDemo();
#if LIVE
  WiFi.mode(WIFI_STA); WiFi.begin(WIFI_SSID, WIFI_PASS);
#endif
  lastInput = millis(); splashUntil = millis() + SPLASH_MS;
  Serial.printf("console ready, %d specimens, %s\n", NSP, LIVE ? "live mode" : "demo mode");
}

void loop() {
  M5.update();
  uint32_t now = millis();
  auto t = M5.Touch.getDetail();
  bool pressed = M5.BtnA.isPressed() || M5.BtnB.isPressed() || t.isPressed();
  bool anyDown = M5.BtnA.wasPressed() || M5.BtnB.wasPressed() || t.wasPressed();
  if (anyDown || pressed) lastInput = now;

  if (asleep) { if (anyDown) wake(); delay(10); return; }
  if (splashUntil) {
    if (dirty) render();
    if (now > splashUntil) { splashUntil = 0; dirty = true; swallow = true; }
    delay(10); return;
  }
  if (swallow) { if (!pressed) swallow = false; delay(10); return; }
  if (now - lastInput > SLEEP_MS) { sleepNow(); return; }
  if (toastUntil) { if (now > toastUntil) { toastUntil = 0; dirty = true; } delay(10); return; }
#if LIVE
  // refresh from the console while idle on the overview or the list
  if (!pressed && (scr == OVERVIEW || scr == LIST) && now - lastSync > 6000 && WiFi.status() == WL_CONNECTED) syncNow();
#endif

  if (scr == OVERVIEW) {
    if (M5.BtnA.wasClicked() || M5.BtnB.wasClicked()) { scr = LIST; dirty = true; }
  } else if (scr == LIST) {
    if (M5.BtnA.wasClicked()) { sel = (sel + 1) % NPEN; dirty = true; }
    if (M5.BtnB.wasClicked()) openPen(order[sel]);
    if (M5.BtnA.wasHold()) { scr = OVERVIEW; dirty = true; }
    if (t.wasPressed()) { tx0 = t.x; ty0 = t.y; tlx = t.x; tly = t.y; }
    if (t.isPressed()) { tlx = t.x; tly = t.y; }
    if (t.wasReleased() && abs(tlx - tx0) < 25 && abs(tly - ty0) < 25 && tly >= ROW_TOP) {
      int r = (tly - ROW_TOP) / ROW_H; if (r >= 0 && r < NPEN) { sel = r; openPen(order[r]); }
    }
  } else if (scr == PEN) {
    if (M5.BtnA.wasClicked()) { pg = (pg + 1) % pages(); dirty = true; }
    if (M5.BtnA.wasHold() && !summaryPage()) { menuSel = 0; scr = MENUSCR; dirty = true; }
    if (M5.BtnB.wasClicked()) { scr = LIST; dirty = true; }
    if (M5.BtnB.wasPressed()) { bStart = now; bFired = false; }
    if (M5.BtnB.isPressed() && !bFired) {                      // hold B to request the vet, with a progress ring
      uint32_t el = now - bStart;
      if (el > 400) { float p = min(1.0f, (el - 400) / (float)(ESC_MS - 400)); holdFrame(p, now); }
      if (el >= ESC_MS) { bFired = true; actVet(); }
    }
    if (M5.BtnB.wasReleased() && arcShown && !bFired) dirty = true;
    if (t.wasPressed()) { tx0 = t.x; ty0 = t.y; tlx = t.x; tly = t.y; }
    if (t.isPressed()) { tlx = t.x; tly = t.y; }
    if (t.wasReleased() && abs(tlx - tx0) < 25 && abs(tly - ty0) < 25 && !summaryPage()) { pg ^= 1; dirty = true; }   // flip photo and why
  } else {
    if (M5.BtnA.wasClicked()) { menuSel = (menuSel + 1) % NMENU; dirty = true; }
    if (M5.BtnB.wasClicked()) {
      if (menuSel == 0) actCheck();
      else if (menuSel == 1) actNormal();
      else if (menuSel == 2) toast("Hold B to confirm", "Keep it pressed");
      else { scr = PEN; dirty = true; }
    }
    if (menuSel == 2) {
      if (M5.BtnB.wasPressed()) { bStart = now; bFired = false; }
      if (M5.BtnB.isPressed() && !bFired) {
        uint32_t el = now - bStart;
        if (el > 400) { float p = min(1.0f, (el - 400) / (float)(ESC_MS - 400)); holdFrame(p, now); }
        if (el >= ESC_MS) { bFired = true; actVet(); }
      }
      if (M5.BtnB.wasReleased() && arcShown && !bFired) dirty = true;      // released early, redraw the menu
    }
  }
  if (dirty) render();
  delay(10);
}

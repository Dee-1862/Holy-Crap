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
//   MENU      A click = next option  B click = choose  (Call the vet needs B held, nothing says so on screen)
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
  #include <WiFiClientSecure.h>
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
  uint8_t p[4]; uint8_t sub[5]; uint8_t rx, ry; char why[3][72]; bool ph;   // ph, the console has a real photo for it
  bool hasSub; int16_t at; uint8_t no;     // five checks measured; seconds into the camera feed (-1 none); number on the camera
};
static bool penOff[NPEN];              // pens with no camera, offline on the console, so they count nowhere
static int penBirds[NPEN] = {-1, -1, -1, -1, -1, -1};   // birds the pen's camera sees now, from the console
static int onlinePens() { int n = 0; for (int i = 0; i < NPEN; i++) n += !penOff[i]; return n; }
static const int MAXSPEC = 24;
static Spec SP[MAXSPEC];
static int NSP = 0;
static bool liveOk = false;            // true while the console answers
static uint32_t lastSync = 0;
// Minutes since each pen was terminated (vet called), -1 when it is not. A termination holds the pen for an hour or
// until it is cleared on the website, and a held pen cannot be terminated again, on the watch or the website.
static int16_t penVet[NPEN] = {-1, -1, -1, -1, -1, -1};
static bool penLocked(int p) { return penVet[p] >= 0; }

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
    memcpy(s.p, d.p, 4); memcpy(s.sub, d.sub, 5); s.rx = d.rx; s.ry = d.ry; s.hasSub = true; s.at = -1;
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
  if (penOff[pen]) return 0;
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
  for (int i = 0; i < NPEN; i++) { m[i] = meanGrade(i, &any); if (!any) m[i] = -1; if (penOff[i]) m[i] = -2; order[i] = i; }   // offline last
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

// A pen shows only its most critical specimen: one still on alert before one marked normal, a suspected
// disease before a healthy one, then the lowest grade, then the newest. penTotal keeps the pen's full count.
static int penTotal = 0;
static bool worse(const Spec& a, const Spec& b) {
  if (counts(a) != counts(b)) return counts(a);
  if ((a.k != 0) != (b.k != 0)) return a.k != 0;
  if (a.grade != b.grade) return a.grade < b.grade;
  return a.mins < b.mins;
}
static bool penChecks = false;         // the open pen has measured checks, so it gets the checklist and radar pages
static void loadPen(int p) {
  gcount = 0; penTotal = 0; penChecks = false;
  for (int i = 0; i < NSP; i++) {
    if (SP[i].pen != p) continue;
    penTotal++; penChecks |= SP[i].hasSub;
    if (!gcount || worse(SP[i], SP[ge[0]])) { ge[0] = i; gcount = 1; }
  }
}
static int pages() { return max(1, 2 * gcount + (penChecks ? 2 : 0)); }   // photo and why of the critical one, then the checklist and radar when measured
static bool specPage() { return pg < 2 * gcount; }
static bool summaryPage() { return penChecks && pg == 2 * gcount; }
static bool radarPage() { return penChecks && pg == 2 * gcount + 1; }
static Spec& curSpec() { return SP[ge[min(pg / 2, gcount - 1)]]; }

// ----- network -----
#if LIVE
static bool http(const char* method, const String& path, const char* body, JsonDocument& out) {
  if (WiFi.status() != WL_CONNECTED) return false;
  // https for a deployed console (Vercel), plain http for a laptop on the same Wi-Fi.
  // The TLS client does not check the certificate yet, fine for a demo, pin Vercel's root before a farm install.
  static WiFiClientSecure tls;
  static WiFiClient plain;
  const bool secure = !strncmp(API_BASE, "https://", 8);
  HTTPClient h; h.setTimeout(secure ? 8000 : 2500);       // a Vercel function can take a few seconds to wake
  bool started;
  if (secure) { tls.setInsecure(); started = h.begin(tls, String(API_BASE) + path); }
  else started = h.begin(plain, String(API_BASE) + path);
  if (!started) return false;
#ifdef VERCEL_BYPASS
  h.addHeader("x-vercel-protection-bypass", VERCEL_BYPASS);   // only for a site behind Vercel Authentication
#endif
  if (body) h.addHeader("Content-Type", "application/json");
  int code = !strcmp(method, "POST") ? h.POST(body ? body : "{}") : h.GET();
  bool ok = code == 200 && !deserializeJson(out, h.getString());
  h.end();
  return ok;
}
// Real specimen photos, 180 by 135 jpegs from the console's public/watch folder. Each is a few kilobytes,
// fetched the first time its page shows and kept, so paging back and forth never waits on Wi-Fi again.
static const int NPHOTO = 12;
static struct { char id[10]; uint8_t* buf; size_t len; } photos[NPHOTO];
static int photoNext = 0;
static bool fetchPhoto(const char* id, const uint8_t** buf, size_t* len) {
  for (auto& p : photos) if (p.buf && !strcmp(p.id, id)) { *buf = p.buf; *len = p.len; return true; }
  if (WiFi.status() != WL_CONNECTED) return false;
  static WiFiClientSecure tls;
  static WiFiClient plain;
  const bool secure = !strncmp(API_BASE, "https://", 8);
  HTTPClient h; h.setTimeout(secure ? 8000 : 2500);
  String url = String(API_BASE) + "/watch/" + id + ".jpg";
  bool started;
  if (secure) { tls.setInsecure(); started = h.begin(tls, url); } else started = h.begin(plain, url);
  if (!started) return false;
#ifdef VERCEL_BYPASS
  h.addHeader("x-vercel-protection-bypass", VERCEL_BYPASS);
#endif
  int code = h.GET(), size = h.getSize();
  if (code != 200 || size <= 0 || size > 40000) { h.end(); return false; }
  uint8_t* b = (uint8_t*)malloc(size);
  if (!b) { h.end(); return false; }
  WiFiClient* st = h.getStreamPtr(); int got = 0; uint32_t t0 = millis();
  while (got < size && millis() - t0 < 8000) { int n = st->readBytes(b + got, size - got); if (n <= 0) delay(5); got += max(n, 0); }
  h.end();
  if (got != size) { free(b); return false; }
  auto& slot = photos[photoNext]; photoNext = (photoNext + 1) % NPHOTO;   // oldest out
  free(slot.buf); strlcpy(slot.id, id, sizeof slot.id); slot.buf = b; slot.len = size;
  *buf = b; *len = size;
  return true;
}
static void syncNow() {
  JsonDocument doc;
  bool was = liveOk;
  liveOk = http("GET", "/api/watch", nullptr, doc);
  lastSync = millis();
  if (liveOk != was) Serial.printf("sync with %s %s\n", API_BASE, liveOk ? "ok" : "failed");   // log changes only
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
    s.hasSub = o["sub"].size() == 5; s.at = o["at"] | -1; s.no = o["no"] | 0;
    s.rx = o["rg"][0] | 50; s.ry = o["rg"][1] | 50;
    for (int j = 0; j < 3; j++) strlcpy(s.why[j], o["why"][j] | "", sizeof s.why[j]);
    s.ph = strlen(o["ph"] | "") > 0;
    NSP++;
  }
  for (JsonObject o : doc["pens"].as<JsonArray>()) { int pi = penIndex(o["id"] | ""); if (pi >= 0) { penOff[pi] = (o["off"] | 0) != 0; penVet[pi] = o["vet"] | -1; penBirds[pi] = o["n"] | -1; } }
  if (scr == PEN || scr == MENUSCR) { loadPen(pen); pg = min(pg, pages() - 1); }
  dirty = true;
}
#endif

// ----- drawing helpers -----
static void text(const char* s, int x, int y, uint16_t col, const lgfx::IFont* f, textdatum_t d = middle_center) {
  M5.Display.setFont(f); M5.Display.setTextSize(1); M5.Display.setTextDatum(d); M5.Display.setTextColor(col); M5.Display.drawString(s, x, y);
}
static void card(int x, int y, int w, int h, int r, uint16_t col) { M5.Display.fillSmoothRoundRect(x, y, w, h, r, col); }
static void photo(const Spec& s, int x, int y) {
#if LIVE
  const uint8_t* rb; size_t rn;                    // the specimen's own photo, when the console has one
  if (s.ph && fetchPhoto(s.id, &rb, &rn)) { M5.Display.drawJpg(rb, rn, x, y); return; }
#endif
  int k = s.k;                                     // otherwise the built-in example of its type
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

  int c[3] = {0, 0, 0}, read = 0;
  for (int i = 0; i < NPEN; i++) { bool any; meanGrade(i, &any); if (!penOff[i] && any) { c[level(i)]++; read++; } }   // like the website: only pens with droppings read
  const int sw = 280, x0 = CX - sw / 2, sy = 248, gap = 4;
  int segs = (c[0] > 0) + (c[1] > 0) + (c[2] > 0);
  float unit = (sw - gap * max(0, segs - 1)) / (float)max(1, read); float x = x0;
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
    text(PEN_NAME[gi], 122, yc, penOff[gi] ? C_TER : C_TXT, &fonts::DejaVu18, middle_left);
    if (penLocked(gi)) text("Terminated", 326, yc, C_BAD, &fonts::DejaVu12, middle_right);
    if (penOff[gi]) snprintf(b, sizeof b, "Offline"); else if (any) snprintf(b, sizeof b, "%.1f", m); else snprintf(b, sizeof b, "n/a");
    text(b, 382, yc, any && !penOff[gi] ? levelColor(level(gi)) : C_TER, penOff[gi] ? &fonts::DejaVu12 : &fonts::DejaVu18, middle_right);
  }
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
  int birds = LIVE ? penBirds[pen] : PEN_BIRDS[pen];   // live: what the camera sees now
  if (birds >= 0) { snprintf(b, sizeof b, "%d birds in view", birds); text(b, CX, 74, C_TER, &fonts::DejaVu12); }
  card(113, 88, 240, 171, 26, C_CARD);
  photo(s, 143, 106);
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
  if (s.st) stateTag(s, 202, 366);
  else {
    if (s.at >= 0) snprintf(b, sizeof b, "Seen at %d:%02d", s.at / 60, s.at % 60); else snprintf(b, sizeof b, "%d min ago", s.mins);
    text(b, 202, 366, C_TER, &fonts::DejaVu12, middle_left);
  }
  snprintf(b, sizeof b, "Most critical of %d", penTotal); text(b, CX, 410, C_TER, &fonts::DejaVu12);
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
  // evidence lines, numbered like the markers on the photo
  int y = 208;
  for (int i = 0; i < 3; i++) {
    if (!s.why[i][0]) continue;
    M5.Display.fillSmoothCircle(94, y + 8, 11, C_CARD2);
    snprintf(b, sizeof b, "%d", i + 1); text(b, 94, y + 8, C_TXT, &fonts::DejaVu12);
    wrap(s.why[i], 116, y, 262, 15, 2, C_TXT);
    y += 58;
  }
  snprintf(b, sizeof b, "Most critical of %d", penTotal); text(b, CX, 410, C_TER, &fonts::DejaVu12);
}
// Pen summary: the five checks in plain words, averaged over the pen's specimens.
static void pageSummary() {
  M5.Display.fillScreen(C_BLK);
  text(PEN_NAME[pen], CX, 46, C_TXT, &fonts::DejaVu24);
  float v[5] = {0}; int n = 0;
  for (int i = 0; i < NSP; i++) { Spec& sp = SP[i]; if (sp.pen != pen || !counts(sp)) continue; n++; for (int j = 0; j < 5; j++) v[j] += sp.sub[j]; }   // whole pen
  for (int j = 0; j < 5; j++) v[j] = n ? v[j] / n : 0;
  card(70, 106, 326, 240, 26, C_CARD);
  for (int j = 0; j < 5; j++) {
    int y0 = 112 + j * 46, yc = y0 + 23; int lv = !n ? 0 : v[j] >= 8 ? 0 : v[j] >= 5 ? 1 : 2;
    if (j > 0) M5.Display.drawFastHLine(94, y0, 278, C_SEP);
    text(AXES[j], 96, yc, C_TXT, &fonts::DejaVu18, middle_left);
    text(n ? WORD[j][lv] : "n/a", 350, yc, lv ? levelColor(lv == 2 ? 2 : 1) : C_SEC, &fonts::DejaVu18, middle_right);
    M5.Display.fillSmoothCircle(374, yc, 5, n ? levelColor(lv) : C_SEP);
  }
  char b[48];
  if (penLocked(pen)) { snprintf(b, sizeof b, "Terminated %d min ago, vet called", penVet[pen]); text(b, CX, 384, C_BAD, &fonts::DejaVu12); }
}
// Pen radar: this pen filled in the status color, the barn average as a dashed line.
static void dashedLine(int x0, int y0, int x1, int y1, uint16_t col) {
  float len = sqrtf((float)((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0)));
  int n = max(1, (int)(len / 11));
  for (int i = 0; i < n; i++) {
    float a = (float)i / n, b = (i + 0.55f) / n;
    M5.Display.drawLine(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, x0 + (x1 - x0) * b, y0 + (y1 - y0) * b, col);
  }
}
static void pageRadar() {
  M5.Display.fillScreen(C_BLK);
  text(PEN_NAME[pen], CX, 46, C_TXT, &fonts::DejaVu24);
  float v[5] = {0}, w[5] = {0}; int n = 0, nb = 0;
  for (int i = 0; i < NSP; i++) { Spec& sp = SP[i]; if (sp.pen != pen || !counts(sp)) continue; n++; for (int j = 0; j < 5; j++) v[j] += sp.sub[j]; }   // whole pen
  for (int i = 0; i < NSP; i++) { if (!counts(SP[i])) continue; nb++; for (int j = 0; j < 5; j++) w[j] += SP[i].sub[j]; }
  for (int j = 0; j < 5; j++) { v[j] = n ? v[j] / n : 0; w[j] = nb ? w[j] / nb : 0; }
  const int cx = CX, cy = 222, R = 96; int lv = level(pen); int px[5], py[5], bx[5], by[5];
  for (int g = 1; g <= 4; g++) {                                   // guide pentagons
    for (int j = 0; j < 5; j++) {
      float a = -PI / 2 + j * 2 * PI / 5, b2 = -PI / 2 + ((j + 1) % 5) * 2 * PI / 5, r = R * g / 4.0f;
      M5.Display.drawLine(cx + cosf(a) * r, cy + sinf(a) * r, cx + cosf(b2) * r, cy + sinf(b2) * r, C_SEP);
    }
  }
  for (int j = 0; j < 5; j++) {
    float a = -PI / 2 + j * 2 * PI / 5;
    M5.Display.drawLine(cx, cy, cx + cosf(a) * R, cy + sinf(a) * R, C_SEP);
    px[j] = cx + cosf(a) * R * v[j] / 10.0f; py[j] = cy + sinf(a) * R * v[j] / 10.0f;
    bx[j] = cx + cosf(a) * R * w[j] / 10.0f; by[j] = cy + sinf(a) * R * w[j] / 10.0f;
  }
  for (int j = 0; j < 5; j++) M5.Display.fillTriangle(cx, cy, px[j], py[j], px[(j + 1) % 5], py[(j + 1) % 5], levelDim(lv));
  for (int j = 0; j < 5; j++) dashedLine(bx[j], by[j], bx[(j + 1) % 5], by[(j + 1) % 5], C_SEC);
  for (int j = 0; j < 5; j++) { M5.Display.drawLine(px[j], py[j], px[(j + 1) % 5], py[(j + 1) % 5], levelColor(lv)); M5.Display.drawLine(px[j] + 1, py[j], px[(j + 1) % 5] + 1, py[(j + 1) % 5], levelColor(lv)); }
  for (int j = 0; j < 5; j++) { M5.Display.fillSmoothCircle(px[j], py[j], 5, levelColor(lv)); M5.Display.fillSmoothCircle(px[j], py[j], 3, C_TXT); }
  for (int j = 0; j < 5; j++) {                                     // labels just outside the pentagon
    float a = -PI / 2 + j * 2 * PI / 5;
    text(AXES[j], cx + cosf(a) * (R + 26), cy + sinf(a) * (R + 22), C_SEC, &fonts::DejaVu12);
  }
  if (penLocked(pen)) { char b[48]; snprintf(b, sizeof b, "Terminated %d min ago, vet called", penVet[pen]); text(b, CX, 396, C_BAD, &fonts::DejaVu12); }
}
static void pageMenu() {
  M5.Display.fillScreen(C_BLK);
  text(PEN_NAME[pen], CX, 64, C_SEC, &fonts::DejaVu18);
  for (int i = 0; i < NMENU; i++) {
    int y = 122 + i * 66; bool on = (i == menuSel);
    card(83, y - 26, 300, 52, 26, on ? C_CARD2 : C_CARD);
    bool held = i == 2 && penLocked(pen);                         // already terminated, shown but locked
    text(held ? "Terminated" : MENU[i], CX, y, held ? C_TER : i == 2 ? (on ? C_BAD : C_SEC) : (on ? C_TXT : C_SEC), &fonts::DejaVu18);
  }
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
static void drawAlien(int cx, int cy, int cell, lgfx::LGFXBase& d = M5.Display) {
  uint16_t outline = d.color565(2, 2, 2), body = d.color565(124, 89, 171), light = d.color565(150, 115, 195);
  int x0 = cx - 10 * cell, y0 = cy - 17 * cell / 2;
  for (int r = 0; r < 17; r++) {
    for (int c = 0; c < 20; c++) {
      char ch = ALIEN[r][c]; if (ch == '.') continue;
      d.fillRect(x0 + c * cell, y0 + r * cell, cell, cell, ch == '#' ? outline : ch == 'l' ? light : body);
    }
  }
}
// ----- the chicken the alien turns into while the ring fills -----
// 18 by 20 pixel art, built with the pixel-art-sprites skill: a blocky chicken that still reads as one in
// silhouette, hue shifted ramps (warm whites, a cool lavender shadow, an orange lit comb) and hard edges.
// O outline, W white, w shadow, R r comb, B b beak, K eye, F feet.
static const char* CHICKEN[20] = {
  "........rR........",
  ".......rRRR.......",
  "......OrRRRO......",
  ".....OWWWWWWWO....",
  ".....OWWWWWWWO....",
  ".....OWWWWWKWOO...",
  ".....OWWWWWWWBBO..",
  ".....OWWWWWWWbbO..",
  ".O...OWWWWWWWRO...",
  ".OO..OWWWWWWWRO...",
  ".OWOOOWWWWWWWO....",
  ".OWWWWWWWWWWWO....",
  ".OWWWWwwwWWWWO....",
  ".OWWWWwwwWWWWO....",
  ".OwWWWWwwWWWWO....",
  ".OwwWWWWWWWWwO....",
  "..OwwwwwwwwwwO....",
  "...OOOOOOOOOO.....",
  "......F..F........",
  ".....FF.FF........",
};
static void alienRGB(char ch, int& R, int& G, int& B) {
  if (ch == '#') { R = 2; G = 2; B = 2; } else if (ch == 'l') { R = 150; G = 115; B = 195; } else { R = 124; G = 89; B = 171; }
}
static void chickRGB(char ch, int& R, int& G, int& B) {
  switch (ch) {
    case 'O': R = 45; G = 32; B = 40; break;    case 'W': R = 252; G = 248; B = 236; break;
    case 'w': R = 196; G = 192; B = 214; break; case 'R': R = 222; G = 44; B = 52; break;
    case 'r': R = 252; G = 112; B = 72; break;  case 'B': R = 250; G = 168; B = 40; break;
    case 'b': R = 214; G = 108; B = 34; break;  case 'K': R = 20; G = 18; B = 24; break;
    default:  R = 244; G = 140; B = 40; break;  // F
  }
}
// Draws pixel art with its bottom edge on bottom, each sprite pixel cw wide and chh tall, so a squash or a
// stretch is just a change of cell size and the feet stay on the ground.
static void drawArt(lgfx::LGFXBase& d, const char* const* art, int rows, int cols, void (*pal)(char, int&, int&, int&), int cx, int bottom, int cw, int chh) {
  int x0 = cx - cols * cw / 2, y0 = bottom - rows * chh, R, G, B;
  for (int r = 0; r < rows; r++) {
    for (int c = 0; c < cols; c++) {
      char ch = art[r][c]; if (ch == '.') continue;
      pal(ch, R, G, B); d.fillRect(x0 + c * cw, y0 + r * chh, cw, chh, d.color565(R, G, B));
    }
  }
}
static void drawChicken(int cx, int cy, int cell, lgfx::LGFXBase& d = M5.Display) {
  drawArt(d, CHICKEN, 20, 18, chickRGB, cx, cy + 10 * cell, cell, cell);
}
// The morph pairs alien pixels with chicken pixels, both read top to bottom, so the top of one becomes the top
// of the other. Three beats from the skill: anticipation (the alien squashes), action (the pixels hop across in a
// wave from the top) and follow-through (the chicken stretches and settles). Every pixel lands on whole pixels.
struct Px { int8_t x, y; char ch; };
static Px MA[20 * 17], MC[18 * 20];
static int nA = 0, nC = 0;
static void morphInit() {
  if (nA) return;
  for (int r = 0; r < 17; r++) for (int c = 0; c < 20; c++) if (ALIEN[r][c] != '.') MA[nA++] = {(int8_t)(c - 10), (int8_t)(r - 17), ALIEN[r][c]};
  for (int r = 0; r < 20; r++) for (int c = 0; c < 18; c++) if (CHICKEN[r][c] != '.') MC[nC++] = {(int8_t)(c - 9), (int8_t)(r - 20), CHICKEN[r][c]};
}
static float ease(float t) { t = constrain(t, 0.0f, 1.0f); return t < 0.5f ? 4 * t * t * t : 1 - powf(-2 * t + 2, 3) / 2; }
static void drawMorph(lgfx::LGFXBase& d, int cx, int bottom, float p) {
  morphInit();
  if (p < 0.2f) {                                                  // anticipation, squash down and out
    float s = ease(p / 0.2f);
    drawArt(d, ALIEN, 17, 20, alienRGB, cx, bottom, 7 + (int)(s + 0.5f), 7 - (int)(2 * s + 0.5f));
    return;
  }
  if (p >= 0.8f) {                                                 // follow-through, stretch up then settle
    float f = (p - 0.8f) / 0.2f; int up = sinf(PI * f) > 0.5f;   // one pixel taller and one thinner, then back
    drawArt(d, CHICKEN, 20, 18, chickRGB, cx, bottom, 6 - up, 6 + up);
    return;
  }
  float q = (p - 0.2f) / 0.6f; int N = max(nA, nC), R1, G1, B1, R2, G2, B2;
  for (int i = 0; i < N; i++) {                                    // action, the pixels hop across
    const Px& a = MA[i * nA / N]; const Px& b = MC[i * nC / N];
    float t = ease((q - 0.4f * i / N) / 0.6f);                     // the wave starts at the top
    alienRGB(a.ch, R1, G1, B1); chickRGB(b.ch, R2, G2, B2);
    int x = cx + (int)(a.x * 7 + (b.x * 6 - a.x * 7) * t), y = bottom + (int)(a.y * 7 + (b.y * 6 - a.y * 7) * t - sinf(PI * t) * 14);
    int sz = t < 0.5f ? 7 : 6;                                     // alien pixels are 7, chicken pixels 6
    d.fillRect(x, y, sz, sz, d.color565(R1 + (R2 - R1) * t, G1 + (G2 - G1) * t, B1 + (B2 - B1) * t));
  }
}
// One frame while B is held: the morph inside the dark circle, drawn off screen so it never flickers, and the
// red ring growing around the edge. p runs from 0 to 1.
static M5Canvas* holdCanvas = nullptr;
static void holdFrame(float p, uint32_t now) {
  auto& d = M5.Display;
  if (!arcShown) { d.fillScreen(C_BLK); arcShown = true; }
  if (!holdCanvas) { holdCanvas = new M5Canvas(&M5.Display); if (!holdCanvas->createSprite(192, 192)) { delete holdCanvas; holdCanvas = nullptr; } }
  if (holdCanvas) {
    holdCanvas->fillScreen(C_BLK); holdCanvas->fillSmoothCircle(96, 96, 95, C_CARD);
    drawMorph(*holdCanvas, 96, 158, p); holdCanvas->pushSprite(CX - 96, CY - 96);
  } else {
    d.fillSmoothCircle(CX, CY, 96, C_CARD); drawMorph(d, CX, CY + 62, p);
  }
  d.fillArc(CX, CY, 216, 224, 270, fmodf(270 + p * 359.0f, 360.0f), C_BAD);
}
static void freeHoldCanvas() { if (holdCanvas) { holdCanvas->deleteSprite(); delete holdCanvas; holdCanvas = nullptr; } }
// Finish screen for the termination. No flashing. Says plainly what happened.
static void terminatedScreen(const char* line1, const char* line2) {
  auto& d = M5.Display;
  d.fillScreen(C_BLK);
  d.fillArc(CX, CY, 216, 224, 0, 360, C_BAD);
  d.fillSmoothCircle(CX, 150, 78, C_CARD);
  drawChicken(CX, 150, 5);
  text("Terminated", CX, 262, C_TXT, &fonts::DejaVu24);
  text(PEN_NAME[pen], CX, 296, C_SEC, &fonts::DejaVu18);
  text(line1, CX, 338, C_TXT, &fonts::DejaVu18);
  text(line2, CX, 366, C_TER, &fonts::DejaVu12);
}
// ----- after the termination: the chicken dances, a gold gauntlet snaps across, and the chicken turns to dust -----
// 22 by 30 pixel art of a gold gauntlet. O outline, d g h dark, mid and light gold, w a highlight,
// o r b p y G the six gems. glow pushes the gems toward white for the snap.
static const char* GAUNTLET[30] = {
  "....OOOOOOOOOOOO......",
  "...OhhgOhhgOhhgOO.....",
  "..OhggdOhggdOhggdOO...",
  "..OgddOOgddOOgddOOhO..",
  "..OdgggggggggggggOhgO.",
  "..OoogrrggbbggppgOhggO",
  "..OoodrrddbbddppdOghgO",
  "..OdgggggggggggggOgggO",
  "..OggggggOOggggggOggdO",
  "..OgggggOyyOgggggOgGGO",
  "..OggggOyhwyOggggOgGGO",
  "..OddggOywyyOggddOgGGO",
  "..OgddgOyyyyOgddgOgddO",
  "..OgggddOyyOddgggOgdO.",
  "..OggggggOOggggggOddO.",
  "..OdgggggggggggggOOO..",
  "...OddddddddddddddO...",
  "...OgdgggdggdgggdgO...",
  "...OgdghgdggdghgdgO...",
  "...OgdghgdggdghgdgO...",
  "...OgdgggdggdgggdgO...",
  "...OgdgggdggdgggdgO...",
  "..OOddddddddddddddOO..",
  ".OgggdgggdgggdgggdggO.",
  ".OghgdghgdghgdghgdhgO.",
  "OgghgdghgdghgdghgdhggO",
  "OgghgdghgdghgdghgdhggO",
  "OgggddgggdgggdgggddggO",
  "OddddddddddddddddddddO",
  ".OOOOOOOOOOOOOOOOOOOO.",
};
static void gauntRGB(char ch, int& R, int& G, int& B, bool& gem) {
  gem = true;
  switch (ch) {
    case 'O': R = 45; G = 30; B = 8; gem = false; break;      case 'd': R = 125; G = 90; B = 20; gem = false; break;
    case 'g': R = 185; G = 140; B = 35; gem = false; break;   case 'h': R = 235; G = 195; B = 85; gem = false; break;
    case 'w': R = 255; G = 255; B = 220; break;               case 'o': R = 245; G = 120; B = 40; break;
    case 'r': R = 225; G = 45; B = 45; break;                 case 'b': R = 70; G = 140; B = 245; break;
    case 'p': R = 160; G = 70; B = 210; break;                case 'y': R = 250; G = 225; B = 40; break;
    default:  R = 60; G = 220; B = 70; break;                 // G
  }
}
// Drawn tilted by deg (negative leans the fist left, across toward the chicken). Each screen pixel looks up the
// sprite pixel under it, so the turned gauntlet keeps hard pixel edges with no gaps.
static void drawGauntlet(lgfx::LGFXBase& d, int cx, int cy, int cell, float glow = 0, float deg = 0) {
  float a = deg * PI / 180, ca = cosf(a), sa = sinf(a);
  const int span = 19 * cell;                                      // past the corner of the 22 by 30 sprite
  for (int dy = -span; dy <= span; dy++) {
    for (int dx = -span; dx <= span; dx++) {
      float sx = ca * dx + sa * dy, sy = -sa * dx + ca * dy;
      int c = (int)floorf(sx / cell + 11), r = (int)floorf(sy / cell + 15);
      if (c < 0 || c >= 22 || r < 0 || r >= 30) continue;
      char ch = GAUNTLET[r][c]; if (ch == '.') continue;
      int R, G, B; bool gem; gauntRGB(ch, R, G, B, gem);
      if (gem && glow > 0) { R += (255 - R) * glow; G += (255 - G) * glow; B += (255 - B) * glow; }
      d.drawPixel(cx + dx, cy + dy, d.color565(R, G, B));
    }
  }
}
// The scene draws into an off-screen canvas over the top of the termination screen, so it never flickers.
// The canvas also carries its slice of the red ring and the dark circle, and the text below stays untouched.
static const int ST_W = 360, ST_H = 190, ST_X = CX - 180, ST_Y = 55, ST_AX = CX - ST_X, ST_AY = 150 - ST_Y;
static void stageBase(M5Canvas& c) {
  c.fillScreen(C_BLK);
  c.fillArc(ST_AX, CY - ST_Y, 216, 224, 0, 360, C_BAD);
  c.fillSmoothCircle(ST_AX, ST_AY, 78, C_CARD);
}
static void snapScene() {
  M5Canvas c(&M5.Display);
  if (!c.createSprite(ST_W, ST_H)) return;                         // no memory, keep the still screen
  const int gx = ST_AX + 110, gy = ST_AY + 8;                      // where the gauntlet stops
  static const int8_t DX[4] = {-10, 0, 10, 0}, DY[4] = {0, -8, 0, -8};
  for (int f = 0; f < 20; f++) {                                   // 1 the chicken dances, side to side with a hop
    stageBase(c); drawChicken(ST_AX + DX[f % 4], ST_AY + DY[f % 4], 5, c); c.pushSprite(ST_X, ST_Y); delay(90);
  }
  for (int f = 0; f <= 10; f++) {                                  // 2 the gauntlet slides in, already leaning
    stageBase(c); drawChicken(ST_AX, ST_AY, 5, c); drawGauntlet(c, gx + (10 - f) * 9, gy, 4, 0, -25);
    c.pushSprite(ST_X, ST_Y); delay(30);
  }
  delay(250);
  // 3 the snap across: wind back (anticipation), swing hard across with the gems flaring (action), settle (follow-through)
  static const int8_t ANG[7] = {-15, -10, -40, -55, -52, -45, -42};
  static const uint8_t GLOW[7] = {0, 0, 60, 100, 70, 40, 15};
  for (int f = 0; f < 7; f++) {
    float a = ANG[f] * PI / 180;
    stageBase(c); drawChicken(ST_AX, ST_AY, 5, c); drawGauntlet(c, gx, gy, 4, GLOW[f] / 100.0f, ANG[f]);
    if (f >= 2 && f <= 4) {                                        // sparks off the top of the fist
      int tx = gx + 60 * sinf(a), ty = gy - 60 * cosf(a);
      for (int i = 0; i < 7; i++) {
        float s = a - PI / 2 - 0.9f + i * 0.3f;
        int sx = tx + cosf(s) * 10, sy = ty + sinf(s) * 10;
        c.drawWideLine(sx, sy, sx + cosf(s) * 12, sy + sinf(s) * 12, 2, c.color565(255, 240, 160));
      }
    }
    c.pushSprite(ST_X, ST_Y);
    if (f == 3) { M5.Power.setVibration(200); delay(70); M5.Power.setVibration(0); } else delay(f < 2 ? 110 : 60);
  }
  delay(250);
  uint8_t rnd[20 * 18];                                            // 4 the dust, each pixel goes at its own moment
  for (auto& v : rnd) v = random(256);
  const int cell = 5, ax = ST_AX - 9 * cell, ay = ST_AY - 10 * cell;
  for (int f = 0; f <= 34; f++) {
    float p = f / 34.0f;
    stageBase(c); drawGauntlet(c, gx, gy, 4, 0, -42);
    for (int r = 0; r < 20; r++) {
      for (int k = 0; k < 18; k++) {
        char ch = CHICKEN[r][k]; if (ch == '.') continue;
        uint8_t rv = rnd[r * 18 + k]; int R, G, B; chickRGB(ch, R, G, B);
        float t = 0.15f + 0.45f * rv / 255.0f + 0.3f * (17 - k) / 17.0f, q = (p - t) / 0.35f;
        if (q <= 0) { c.fillRect(ax + k * cell, ay + r * cell, cell, cell, c.color565(R, G, B)); continue; }
        if (q >= 1) continue;                                      // gone
        int sz = max(1, (int)(cell * (1 - q)));
        int x = ax + k * cell - q * 55 - (int)(((rv >> 3) & 7) - 3) * q * 3, y = ay + r * cell - q * 30 - (rv & 7) * q * 3;
        c.fillRect(x, y, sz, sz, c.color565(R + (110 - R) * q, G + (95 - G) * q, B + (85 - B) * q));   // drifts away as dust
      }
    }
    c.pushSprite(ST_X, ST_Y); delay(25);
  }
  c.deleteSprite();
}
static void toast(const char* m, const char* sub) {
  card(CX - 150, CY - 50, 300, 100, 34, C_CARD2);
  text(m, CX, CY - 12, C_TXT, &fonts::DejaVu18);
  text(sub, CX, CY + 24, C_TER, &fonts::DejaVu12);
  toastUntil = millis() + 1700;
}
// A pen whose camera reads flock behaviour only: droppings are too small to read from a whole-pen view.
static void pageNoDroppings() {
  char b[40];
  M5.Display.fillScreen(C_BLK);
  text(PEN_NAME[pen], CX, 150, C_TXT, &fonts::DejaVu24);
  if (penBirds[pen] >= 0) { snprintf(b, sizeof b, "%d birds in view", penBirds[pen]); text(b, CX, 190, C_SEC, &fonts::DejaVu18); }
  text("No droppings read", CX, 250, C_TXT, &fonts::DejaVu18);
  text("This camera watches the whole pen", CX, 282, C_TER, &fonts::DejaVu12);
  text("for flock behaviour", CX, 302, C_TER, &fonts::DejaVu12);
}
static void render() {
  if (splashUntil) pageActive();
  else if (scr == OVERVIEW) pageOverview();
  else if (scr == LIST) pageList();
  else if (scr == MENUSCR) pageMenu();
  else if (!gcount) pageNoDroppings();
  else if (summaryPage()) pageSummary();
  else if (radarPage()) pageRadar();
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
static void lockedToast() { char b[40]; snprintf(b, sizeof b, "%d min ago, clear it on the website", penVet[pen]); toast("Already terminated", b); }
static void actCheck() { setState(ge[min(pg / 2, gcount - 1)], 1, "check"); toast("I'll check it", where()); scr = PEN; }
static void actNormal() { setState(ge[min(pg / 2, gcount - 1)], 2, "normal"); toast("Marked normal", "Removed from alerts"); scr = PEN; loadPen(pen); pg = 0; }   // the next most critical takes its place
// Vet request. Shows the alien, then says plainly what happened. No phone call is placed.
static void actVet() {
  const char* line1 = "Vet request saved"; const char* line2 = where();
#if LIVE
  JsonDocument d; char body[48]; snprintf(body, sizeof body, "{\"specimenId\":\"%s\"}", specPage() ? curSpec().id : "");
  liveOk = http("POST", String("/api/pens/") + PEN_ID[pen] + "/vet", body, d);
  if (liveOk) {
    if (d["duplicate"] | false) { line1 = "Already terminated"; line2 = "Clear it on the website"; }
    else if (!strcmp(d["call"]["delivered"] | "", "sent")) { line1 = "Vet notified"; line2 = "Message sent"; }
    else if (!strcmp(d["call"]["delivered"] | "", "failed")) { line1 = "Saved, not sent"; line2 = "Check the webhook"; }
    else line2 = "No phone service connected yet";
  }
#else
  line2 = "Demo data, nothing sent";
#endif
  penVet[pen] = 0;                                               // held from now, the next sync confirms it
  M5.Power.setVibration(255); delay(160); M5.Power.setVibration(0);     // one short buzz, no flashing
  terminatedScreen(line1, line2);
  freeHoldCanvas(); snapScene();
  toastUntil = millis() + 2500; swallow = true;                   // presses made during the scene do not count
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

#if LIVE
  // refresh from the console on every screen, and while asleep, so the health board and the pen pages stay current
  static int wifiWas = -1;
  if ((int)WiFi.status() != wifiWas) {                    // log Wi-Fi changes, so the laptop can see what happened
    wifiWas = WiFi.status();
    if (wifiWas == WL_CONNECTED) Serial.printf("wifi connected to %s as %s\n", WIFI_SSID, WiFi.localIP().toString().c_str());
    else Serial.printf("wifi status %d\n", wifiWas);
  }
  uint32_t every = asleep ? 30000 : 6000;                 // slower while the screen is off
  bool idle = !pressed && now - lastInput > 1500 && !splashUntil && !toastUntil;   // never stall a press mid-use
  if (idle && now - lastSync > every && WiFi.status() == WL_CONNECTED) syncNow();
#endif

  if (asleep) { if (anyDown) wake(); delay(10); return; }
  if (splashUntil) {
    if (dirty) render();
    if (now > splashUntil) { splashUntil = 0; dirty = true; swallow = true; }
    delay(10); return;
  }
  if (swallow) { if (!pressed) swallow = false; delay(10); return; }
  if (now - lastInput > SLEEP_MS) { sleepNow(); return; }
  if (toastUntil) { if (now > toastUntil) { toastUntil = 0; dirty = true; } delay(10); return; }

  if (scr == OVERVIEW) {
    if (M5.BtnA.wasClicked() || M5.BtnB.wasClicked()) { scr = LIST; dirty = true; }
  } else if (scr == LIST) {
    if (M5.BtnA.wasClicked()) { sel = (sel + 1) % NPEN; dirty = true; }
    if (M5.BtnB.wasClicked() && !penOff[order[sel]]) openPen(order[sel]);   // no camera, nothing to open
    if (M5.BtnA.wasHold()) { scr = OVERVIEW; dirty = true; }
    if (t.wasPressed()) { tx0 = t.x; ty0 = t.y; tlx = t.x; tly = t.y; }
    if (t.isPressed()) { tlx = t.x; tly = t.y; }
    if (t.wasReleased() && abs(tlx - tx0) < 25 && abs(tly - ty0) < 25 && tly >= ROW_TOP) {
      int r = (tly - ROW_TOP) / ROW_H; if (r >= 0 && r < NPEN) { sel = r; if (penOff[order[r]]) dirty = true; else openPen(order[r]); }
    }
  } else if (scr == PEN) {
    if (M5.BtnA.wasClicked()) { pg = (pg + 1) % pages(); dirty = true; }
    if (M5.BtnA.wasHold() && specPage()) { menuSel = 0; scr = MENUSCR; dirty = true; }
    if (M5.BtnB.wasClicked()) { scr = LIST; dirty = true; }
    if (M5.BtnB.wasPressed()) { bStart = now; bFired = false; }
    if (M5.BtnB.isPressed() && !bFired) {                      // hold B to request the vet, with a progress ring
      uint32_t el = now - bStart;
      if (el > 400 && penLocked(pen)) { bFired = true; lockedToast(); }   // already terminated, no ring
      else if (el > 400) { float p = min(1.0f, (el - 400) / (float)(ESC_MS - 400)); holdFrame(p, now); }
      if (el >= ESC_MS && !bFired) { bFired = true; actVet(); }
    }
    if (M5.BtnB.wasReleased() && arcShown && !bFired) dirty = true;
    if (t.wasPressed()) { tx0 = t.x; ty0 = t.y; tlx = t.x; tly = t.y; }
    if (t.isPressed()) { tlx = t.x; tly = t.y; }
    if (t.wasReleased() && abs(tlx - tx0) < 25 && abs(tly - ty0) < 25 && specPage()) { pg ^= 1; dirty = true; }   // flip photo and why
  } else {
    if (M5.BtnA.wasClicked()) { menuSel = (menuSel + 1) % NMENU; dirty = true; }
    if (M5.BtnB.wasClicked()) {
      if (menuSel == 0) actCheck();
      else if (menuSel == 1) actNormal();
      else if (menuSel == 2) { if (penLocked(pen)) lockedToast(); else toast("Hold B to confirm", "Keep it pressed"); }
      else { scr = PEN; dirty = true; }
    }
    if (menuSel == 2) {
      if (M5.BtnB.wasPressed()) { bStart = now; bFired = false; }
      if (M5.BtnB.isPressed() && !bFired) {
        uint32_t el = now - bStart;
        if (el > 400 && penLocked(pen)) { bFired = true; lockedToast(); }
        else if (el > 400) { float p = min(1.0f, (el - 400) / (float)(ESC_MS - 400)); holdFrame(p, now); }
        if (el >= ESC_MS && !bFired) { bFired = true; actVet(); }
      }
      if (M5.BtnB.wasReleased() && arcShown && !bFired) dirty = true;      // released early, redraw the menu
    }
  }
  if (dirty) render();
  delay(10);
}

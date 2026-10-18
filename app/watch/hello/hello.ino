// StopWatch bring-up test: display, buttons, serial. No Wi-Fi yet.
#include <M5Unified.h>

static int presses = 0;

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);
  M5.Display.setRotation(0);
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setTextDatum(middle_center);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(2);
  M5.Display.drawString("Holy-Crap", M5.Display.width() / 2, M5.Display.height() / 2 - 30);
  M5.Display.setTextSize(1);
  M5.Display.drawString("watch bring-up", M5.Display.width() / 2, M5.Display.height() / 2 + 10);
  Serial.printf("boot ok, board id %d, display %dx%d\n", (int)M5.getBoard(), M5.Display.width(), M5.Display.height());
}

static void show(const char* msg) {
  M5.Display.fillRect(0, M5.Display.height() / 2 + 40, M5.Display.width(), 60, TFT_BLACK);
  M5.Display.drawString(msg, M5.Display.width() / 2, M5.Display.height() / 2 + 60);
  Serial.println(msg);
}

void loop() {
  M5.update();
  char buf[48];
  if (M5.BtnA.wasClicked())      { snprintf(buf, sizeof buf, "A click #%d", ++presses); show(buf); }
  if (M5.BtnA.wasHold())         { show("A hold"); }
  if (M5.BtnB.wasClicked())      { snprintf(buf, sizeof buf, "B click #%d", ++presses); show(buf); }
  if (M5.BtnB.wasHold())         { show("B hold"); }
  auto t = M5.Touch.getDetail();
  if (t.wasPressed())            { snprintf(buf, sizeof buf, "touch %d,%d", t.x, t.y); show(buf); }
  delay(10);
}

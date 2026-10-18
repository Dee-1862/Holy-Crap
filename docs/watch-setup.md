# StopWatch Setup Guide (M5Stack Core StopWatch, SKU C152)

Sources: M5Stack docs (https://docs.m5stack.com/en/core/StopWatch, https://docs.m5stack.com/en/products/sku/C152, Arduino pages under https://docs.m5stack.com/en/arduino/stopwatch/ for program, button, battery, speaker) and CNX Software / Mouser. Found by search on 2026-10-17; flashing details are partly from a third-party guide that says it was not tested on a physical kit. Verify on the device.

## What it is
- Brand: **M5Stack** (maker of modular ESP32 development devices). Product: **Core StopWatch**, SKU **C152**, sold as the "StopWatch Dev Kit".
- ESP32-S3R8 (dual-core 240 MHz, 8 MB PSRAM, 16 MB flash), Wi-Fi 4 (2.4 GHz) + BLE 5, 1.75" round AMOLED touch (466x466), 2 programmable buttons + 1 power button, vibration motor, 1 W speaker, microphone, IMU, RTC, 450 mAh battery, USB-C for charging and programming, Grove + GPIO.
- It is a microcontroller, not a QNX device: it runs Arduino/ESP-IDF firmware that we write. It never talks to the Pi directly.

## How it connects to our system
```
StopWatch --(Wi-Fi, MQTT)--> Broker <--(Wi-Fi, MQTT)-- Pi 5 (or the simulator)
```
The watch and the Pi are both clients of the same broker. So the watch is built and tested against the **simulator** first; swapping in the real Pi later changes nothing on the watch (same broker address, same topics).

## Steps
1. **Dev setup (PC):** Arduino IDE with the M5Stack board package (docs say version >= 3.3.7, board option M5StopWatch) and libraries M5Unified (>= 0.2.15) and M5GFX (>= 0.2.21); or PlatformIO using the `m5stack-stopwatch` environment from the M5Stack docs (board `esp32s3box`, Arduino framework, libraries M5Unified, M5GFX, M5PM1, M5IOE1). Follow the official "program" page for exact versions.
2. **Flash:** connect USB-C; if upload fails, put it in download mode (docs: hold the reset/power button about 2 s). Upload an example (e.g. a BarGraph/hello world) to confirm display and buttons work.
3. **Hello network:** connect to Wi-Fi (**2.4 GHz only**; the ESP32-S3 can't use 5 GHz). Barn or hackathon Wi-Fi must offer 2.4 GHz and allow device-to-device traffic (some venue networks isolate clients).
4. **MQTT:** add an MQTT client library (e.g. PubSubClient or the ESP-IDF MQTT client), connect to the broker, subscribe to `holycrap/v1/{site_id}/alerts`, publish acks to `.../alerts/{alert_id}/ack`.
5. **UI:** screens from system-architecture.md section 5 (home, group list, alert popup). Buttons per the docs' button page: call `M5.update()` each loop and read button state; short/long press mapping:
   - Button 1 short = acknowledge, long = false alarm
   - Button 2 long (~2 s) = escalate; vibrate to confirm
6. **Offline state:** show OFFLINE when Wi-Fi or broker is lost; queue acks and send after reconnect.
7. **Battery:** measure real runtime with Wi-Fi on; use screen timeouts and wake on alert.
8. **Demo against the simulator** (fake abnormal events from the backend) before the Pi exists.
9. **Switch to the real Pi:** point the Pi's publisher at the same broker. No watch change.

## Config and secrets
Keep Wi-Fi name/password and broker credentials in a local `secrets.h` that is git-ignored. Commit a `secrets.example.h` instead.

## Open questions / unverified
- Whether the two programmable buttons can distinguish short and long presses with the docs' button API (expected, check).
- Power-button behavior: the docs list a separate power button; confirm it isn't one of the two programmable ones.
- Battery life under Wi-Fi MQTT.
- Whether a 2.4 GHz network is available at the demo venue.

## Done on this PC (2026-10-17)
- Watch detected as `COM18` (Espressif USB JTAG/serial, VID 303A PID 1001).
- Tools: arduino-cli 1.5.1 with the `esp32:esp32` core 3.3.12 (the stock Espressif core has no StopWatch entry, so we use the board from M5Stack's PlatformIO recipe: `esp32:esp32:esp32s3box`). Libraries installed: M5Unified 0.2.26, M5GFX 0.2.33, M5PM1 1.0.7, M5IOE1 1.0.9, PubSubClient 2.8.
- Firmware: `app/watch/console/console.ino` (the first bring-up sketch was removed once the console firmware replaced it).
- Build: `arduino-cli compile --fqbn esp32:esp32:esp32s3box app/watch/console`
- Flash: `arduino-cli upload -p COM18 --fqbn esp32:esp32:esp32s3box app/watch/console`
- Result: compiled (16% of flash), flashed and hash-verified, boots; serial prints `boot ok, board id 30, display 468x468`. Screen and buttons not yet confirmed visually by anyone.
- Note: this replaced the watch's factory firmware. The official M5Stack board package (docs say >= 3.3.7, board option M5StopWatch) is the alternative if the generic board misbehaves (display, battery, power).

## Live mode (2026-10-17)
The watch runs on built in demo data until `app/watch/console/secrets.h` exists. With it, the watch joins Wi-Fi and talks to the console (`app/console`) so the actions really work.

1. Copy `secrets.example.h` to `secrets.h` in `app/watch/console/` and fill in the Wi-Fi name, password and the console address. `secrets.h` is ignored by git.
2. Run the console so the watch can reach it: `cd app/console`, then `npm run dev -- -H 0.0.0.0`. Allow port 3000 through the firewall of that machine. Use a 2.4 GHz network.
3. Flash with `arduino-cli compile` and `arduino-cli upload` as in the steps above. Needs the ArduinoJson library (installed).

What the watch does in live mode
- Every 6 seconds on the overview or the board it reads `/api/watch` (about 2.3 KB).
- I'll check it, Looks normal and Call the vet are sent to the console and show up on the web and phone apps within a few seconds.
- Calling the vet only records a request. Real phone calls and any message service are on hold. If the console has `VET_WEBHOOK_URL` set, the request is posted there.
- Not yet tested on a Wi-Fi network. The live code compiles, and the API it calls was tested with curl.

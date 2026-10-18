// Copy this file to secrets.h and fill it in. secrets.h is ignored by git.
// Without secrets.h the watch runs on built in demo data and nothing leaves the device.
//
// The watch needs the console running on a machine it can reach, for example
//   cd app/console && npm run dev -- -H 0.0.0.0
// and a 2.4 GHz Wi-Fi network (the ESP32 S3 cannot use 5 GHz).
// Allow the port through the firewall of the machine that runs the console.
#pragma once

#define WIFI_SSID "your wifi name"
#define WIFI_PASS "your wifi password"
#define API_BASE  "http://192.168.1.50:3000"

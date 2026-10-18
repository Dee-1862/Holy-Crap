// Copy this file to secrets.h and fill it in. secrets.h is ignored by git.
// Without secrets.h the watch runs on built in demo data and nothing leaves the device.
//
// API_BASE is the console the watch polls every few seconds, so it updates without reflashing.
// Either the deployed console, e.g. "https://holy-crap.vercel.app" (https works, no trailing slash),
// or a machine on the same Wi-Fi running the console, for example
//   cd app/console && npm run dev -- -H 0.0.0.0
// and a 2.4 GHz Wi-Fi network (the ESP32 S3 cannot use 5 GHz).
// Allow the port through the firewall of the machine that runs the console.
#pragma once

#define WIFI_SSID "your wifi name"
#define WIFI_PASS "your wifi password"
#define API_BASE  "http://192.168.1.50:3000"
// Only if API_BASE is a Vercel address behind Vercel Authentication (preview and branch addresses are):
// #define VERCEL_BYPASS "the Protection Bypass for Automation secret from the project settings"

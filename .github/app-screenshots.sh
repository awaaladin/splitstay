#!/bin/bash
# Installs the app on the emulator and saves what each screen really looks like.
mkdir -p shots
adb install android/app/build/outputs/apk/debug/app-debug.apk
adb logcat -c
open() {
  adb shell am start -W -n com.splitpay.app/.MainActivity
  sleep 25
  adb exec-out screencap -p > "shots/$1.png"
}
open 1-start
adb shell input tap 540 1500
sleep 3
adb exec-out screencap -p > shots/2-after-tap.png
adb shell input keyevent KEYCODE_BACK
sleep 5
adb exec-out screencap -p > shots/3-after-back.png
adb shell pidof com.splitpay.app > shots/process.txt || echo "not running" > shots/process.txt
adb logcat -d -b crash > shots/crash.txt

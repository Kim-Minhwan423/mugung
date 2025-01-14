#!/bin/bash
# Chrome 설치
echo "🔹 Installing Google Chrome..."
curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o chrome.deb
apt-get update
apt-get install -y ./chrome.deb
rm chrome.deb

# Chrome 설치 확인
echo "🔹 Google Chrome Version:"
google-chrome --version

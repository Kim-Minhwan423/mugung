#!/bin/bash

# ✅ Chrome 설치 경로 설정
export CHROME_BIN=/usr/bin/google-chrome
export CHROME_PATH=/usr/bin/google-chrome

# ✅ Chrome 설치 스크립트 (Render에서 직접 다운로드)
echo "🔹 Installing Google Chrome..."
wget -q -O chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i chrome.deb || sudo apt-get -f install -y
rm chrome.deb

# ✅ Chrome 버전 확인
echo "🔹 Google Chrome Version:"
google-chrome --version

# ✅ Python 패키지 설치
pip install -r requirements.txt

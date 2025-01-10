#!/bin/bash

# 최신 Chrome 다운로드 및 설치
echo "Installing Chrome..."
wget -q -O chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
apt update && apt install -y ./chrome.deb
rm chrome.deb

# 최신 ChromeDriver 다운로드 및 설치
echo "Installing ChromeDriver..."
CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d. -f1)
wget -q -O chromedriver.zip "https://chromedriver.storage.googleapis.com/$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION)/chromedriver_linux64.zip"
unzip chromedriver.zip
chmod +x chromedriver
mv chromedriver /usr/local/bin/
rm chromedriver.zip

echo "Installation complete."

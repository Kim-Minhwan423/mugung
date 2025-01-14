#!/bin/bash

set -e  # 스크립트 중단 시 오류 출력

echo "🔹 Installing Google Chrome..."
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb || true
sudo apt-get -fy install

echo "🔹 Verifying Google Chrome Installation..."
google-chrome --version || (echo "Google Chrome installation failed!" && exit 1)

echo "🔹 Installing ChromeDriver..."
wget -q https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip
unzip -o chromedriver_linux64.zip
sudo mv chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver

echo "🔹 Verifying ChromeDriver Installation..."
chromedriver --version || (echo "ChromeDriver installation failed!" && exit 1)

echo "🔹 Installing Python dependencies..."
pip install -r requirements.txt

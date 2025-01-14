#!/bin/bash

echo "🔹 Installing Google Chrome..."
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
dpkg -i google-chrome-stable_current_amd64.deb || true
apt-get -fy install

echo "🔹 Google Chrome Version:"
google-chrome --version

echo "🔹 Installing ChromeDriver..."
wget https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip
unzip chromedriver_linux64.zip
mv chromedriver /usr/local/bin/
chmod +x /usr/local/bin/chromedriver

echo "🔹 Installing Python dependencies..."
pip install -r requirements.txt

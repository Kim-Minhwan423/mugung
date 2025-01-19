import os
import time
import gspread
import traceback
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# ================================
# 1. Google Sheets API 인증 설정
# ================================
# User-Agent 설정
user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    " AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/120.0.0.0 Safari/537.36"
)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# GitHub Actions용: /tmp/keyfile.json 경로 (헤드리스 서버에서)
json_path = "/tmp/keyfile.json"  
creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
client = gspread.authorize(creds)

# 스프레드시트 열기 (예시)
spreadsheet = client.open("청라 일일/월말 정산서")  # 스프레드시트 이름

sheet_inventory = spreadsheet.worksheet("재고")    # '재고' 시트 선택
sheet_report = spreadsheet.worksheet("무궁 청라")  # '무궁 청라' 시트 선택

# ================================
# 2. Chrome WebDriver 실행
# ================================
# --- 헤드리스 모드 + 한국어/ko-KR 설정 ---
options = webdriver.ChromeOptions()

# 1) Headless (GUI 없이 동작)
options.add_argument("--headless=new")  # 최신 headless 모드 사용

# 2) 서버 환경 안정성 옵션
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")

# 3) 언어 설정
options.add_argument("--lang=ko-KR")
options.add_experimental_option("prefs", {
    "intl.accept_languages": "ko,ko-KR"
})

# 4) 기타 설정
options.add_argument("--window-size=1920,1080")
options.add_argument(f"user-agent={user_agent}")

# ChromeDriver 설치 및 WebDriver 초기화
driver = webdriver.Chrome(
    service=ChromeService(ChromeDriverManager().install()),
    options=options
)

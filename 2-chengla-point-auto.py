import os
import sys
import re
import time
import datetime
import logging
import traceback
import base64
import json
import uuid
import tempfile

# -----------------------------
# Selenium
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
    ElementClickInterceptedException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# WebDriver Manager
from webdriver_manager.chrome import ChromeDriverManager

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

###############################################################################
# 1. 로깅 설정
###############################################################################
def setup_logging(log_filename='script.log'):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 콘솔 로그
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_formatter = logging.Formatter('%(message)s')
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    # 파일 로그
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

###############################################################################
# 2. 환경 변수 불러오기
###############################################################################
def get_environment_variables():
    point_id = os.getenv("CHENGLA_POINT_ID")
    point_pw = os.getenv("CHENGLA_POINT_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not point_id or not point_pw:
        raise ValueError("CHENGLA_POINT_ID 혹은 CHENGLA_POINT_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    return point_id, point_pw, service_account_json_b64

###############################################################################
# 3. Chrome 드라이버 세팅
###############################################################################
def get_chrome_driver(use_profile=False):
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/110.0.5481.77 Safari/537.36"
    )
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1200,700")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        }
    )
    logging.info("ChromeDriver 초기화 성공")
    return driver

###############################################################################
# 4. 로그인 및 팝업 닫기
###############################################################################
def login_point(driver, point_id, point_pw):
    driver.get("https://xn--3j1b74x8mfjtk.com/visits/stats/550")
    logging.info("포인트 로그인 페이지 접속 완료")

    id_selector = "body > div > form > div:nth-child(3) > input[type=text]"
    pw_selector = "body > div > form > div:nth-child(4) > input[type=password]"
    login_btn_selector = "body > div > form > button"

    try:
        WebDriverWait(driver, 30).until(EC.visibility_of_element_located((By.CSS_SELECTOR, id_selector)))
        driver.find_element(By.CSS_SELECTOR, id_selector).send_keys(point_id)
        logging.info("아이디 입력 완료")
        driver.find_element(By.CSS_SELECTOR, pw_selector).send_keys(point_pw)
        logging.info("비밀번호 입력 완료")
        driver.find_element(By.CSS_SELECTOR, login_btn_selector).click()
        logging.info("로그인 버튼 클릭")
    except TimeoutException:
        logging.warning("로그인 페이지 로딩 Timeout")
    time.sleep(5)

###############################################################################
# 5. 포인트 적립&사용 조회
###############################################################################
def go_visitor_usage_selector(driver):
    visitor_usage_xpath = "/html/body/div/div[2]/div[1]/div/div[3]/a"
    try:
        WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, visitor_usage_xpath)))
        driver.find_element(By.XPATH, visitor_usage_xpath).click()
        logging.info("포인트 적립&사용 조회 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("포인트 적립&사용 조회 메뉴 버튼을 찾지 못함")
    time.sleep(3)

    today_selector = "#periodFilter > option:nth-child(2)"
    try:
        WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.CSS_SELECTOR, today_selector)))
        driver.find_element(By.CSS_SELECTOR, today_selector).click()
        logging.info("오늘 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("오늘 메뉴 버튼을 찾지 못함")

def get_today_usage(driver):
    usage_selector = "#filteredUsedValue"
    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.find_element(By.CSS_SELECTOR, usage_selector).text.strip() != ''
        )
        text = driver.find_element(By.CSS_SELECTOR, usage_selector).text.strip()
        usage_value = re.sub(r'[^\d]', '', text)
        logging.info(f"오늘 사용금액: {usage_value}")
        return int(usage_value) if usage_value else -1
    except Exception as e:
        logging.error(f"사용금액 파싱 오류: {e}")
        return -1

def get_today_saved_count(driver):
    status_xpath = '//*[@id="filteredCustomersValue"]'
    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.find_element(By.XPATH, status_xpath).text.strip() != ''
        )
        text = driver.find_element(By.XPATH, status_xpath).text.strip()
        logging.info(f"[디버그] 적립건수 텍스트: '{text}'")
        saved_count = int(re.sub(r'[^\d]', '', text))
        logging.info(f"오늘 적립건수: {saved_count}")
        return saved_count
    except Exception as e:
        logging.error(f"적립건수 파싱 오류: {e}")
        return -1



###############################################################################
# 6. Google Sheets 업데이트
###############################################################################
def get_gspread_client_from_b64(service_account_json_b64):
    service_account_json = base64.b64decode(service_account_json_b64).decode('utf-8')

    tmp_credentials_file = "service_account_credentials.json"
    with open(tmp_credentials_file, "w", encoding="utf-8") as f:
        f.write(service_account_json)

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(tmp_credentials_file, scope)
    client = gspread.authorize(creds)
    return client

def batch_update_sheet(service_account_json_b64, usage_value, visitor_count):
    client = get_gspread_client_from_b64(service_account_json_b64)
    spreadsheet = client.open("청라 일일/월말 정산서")
    worksheet = spreadsheet.worksheet("청라")

    today_day = datetime.datetime.now().day
    row_index = today_day + 2

    ak_cell = f"AK{row_index}"
    ai_cell = f"AI{row_index}"

    updates = [
        {"range": ak_cell, "values": [[usage_value]]},
        {"range": ai_cell, "values": [[visitor_count]]}
    ]
    worksheet.batch_update(updates)
    logging.info(f"배치 업데이트 완료: {ak_cell}={usage_value}, {ai_cell}={visitor_count}")

###############################################################################
# 메인 실행
###############################################################################
def main():
    setup_logging()

    try:
        point_id, point_pw, service_account_json_b64 = get_environment_variables()
        driver = get_chrome_driver(use_profile=False)

        login_point(driver, point_id, point_pw)

        go_visitor_usage_selector(driver)
        usage_value = get_today_usage(driver)
        visitor_count = get_today_saved_count(driver)

        batch_update_sheet(service_account_json_b64, usage_value, visitor_count)

    except Exception as e:
        logging.error(f"스크립트 실행 중 에러: {e}")
        logging.error(traceback.format_exc())
    finally:
        if 'driver' in locals():
            driver.quit()

if __name__ == "__main__":
    main()

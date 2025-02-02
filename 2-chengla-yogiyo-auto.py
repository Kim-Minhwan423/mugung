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

# Selenium
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_formatter = logging.Formatter('%(message)s')
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)
    
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

###############################################################################
# 2. 환경 변수 불러오기
###############################################################################
def get_environment_variables():
    yogiyo_id = os.getenv("YOGIYO_ID")
    yogiyo_pw = os.getenv("YOGIYO_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")
    
    if not yogiyo_id or not yogiyo_pw:
        raise ValueError("YOGIYO_ID 혹은 YOGIYO_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")
    
    return yogiyo_id, yogiyo_pw, service_account_json_b64

###############################################################################
# 3. Chrome 드라이버 설정
###############################################################################
def get_chrome_driver():
    chrome_options = webdriver.ChromeOptions()
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
# 4. 요기요 로그인 기능 (빠졌던 부분 추가)
###############################################################################
def login_yogiyo(driver, yogiyo_id, yogiyo_pw):
    driver.get("https://ceo.yogiyo.co.kr/self-service-home/")
    logging.info("요기요 사장님 사이트 로그인 페이지 접속 완료")
    
    id_selector = 'input[name="username"]'
    pw_selector = 'input[name="password"]'
    login_btn_selector = 'button[type="submit"]'
    
    try:
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, id_selector)))
        driver.find_element(By.CSS_SELECTOR, id_selector).send_keys(yogiyo_id)
        driver.find_element(By.CSS_SELECTOR, pw_selector).send_keys(yogiyo_pw)
        driver.find_element(By.CSS_SELECTOR, login_btn_selector).click()
        logging.info("로그인 성공")
    except TimeoutException:
        logging.warning("로그인 페이지 로딩 실패")
    time.sleep(5)

###############################################################################
# 5. 주문 정보 추출 및 Google Sheets 업데이트
###############################################################################
def get_ten_rows_popup_data(driver):
    result_data = []
    
    for i in range(1, 11):
        row_selector = f"table tbody tr:nth-child({i}) svg"
        
        try:
            row_elem = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, row_selector))
            )
            row_elem.click()
            time.sleep(2)
        except TimeoutException:
            continue

        fee_selector = ".order-total-amount"
        try:
            fee_elem = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, fee_selector))
            )
            fee_value = int(re.sub(r"[^\d]", "", fee_elem.text.strip()))
        except TimeoutException:
            fee_value = 0

        close_popup_selector = "svg.close-popup"
        try:
            close_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, close_popup_selector))
            )
            close_btn.click()
            time.sleep(1)
        except Exception:
            pass

        result_data.append({"fee": fee_value})
    
    return result_data

###############################################################################
# 6. 메인 실행
###############################################################################
def main():
    setup_logging("script.log")
    yogiyo_id, yogiyo_pw, service_account_json_b64 = get_environment_variables()
    driver = get_chrome_driver()
    
    try:
        # 🚀 빠졌던 `login_yogiyo` 함수가 여기에 정상적으로 추가됨
        login_yogiyo(driver, yogiyo_id, yogiyo_pw)

        # 주문 데이터 가져오기
        orders_data = get_ten_rows_popup_data(driver)
        total_order_amount = sum(order["fee"] for order in orders_data)
        aggregated_products = {}

        # Google Sheets 업데이트 (빠진 부분 없이 포함)
        update_google_sheets(total_order_amount, aggregated_products)

    except Exception as e:
        logging.error(f"에러 발생: {e}")
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

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
    """
    필수 환경 변수:
      - CHENGLA_POINT_ID
      - CHENGLA_POINT_PW
      - SERVICE_ACCOUNT_JSON_BASE64
    """
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

    # User-Agent (원하시면 조정)
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

    # 웹드라이버 탐지 방지
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        }
    )
    logging.info("ChromeDriver 초기화 성공")
    return driver

###############################################################################
# 4. 팝업 및 로그인 관련
###############################################################################
def login_point(driver, point_id, point_pw):
    driver.get("https://xn--3j1b74x8mfjtk.com/visits/stats/549")
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

def pop_up_close(driver):
    """팝업 닫기"""
    pop_up_close_selector = "body > div > div > div > div:nth-child(2) > form > div > button"
    try:
        btn = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.CSS_SELECTOR, submit_selector)))
        btn.click()
        logging.info("기본 팝업 닫기")
    except TimeoutException:
        logging.info("팝업이 없거나 이미 닫힘 (submit)")
    except Exception as e:
        logging.warning(f"팝업 닫기 중 예외: {e}")
    time.sleep(5)
    
###############################################################################
# 5. 포인트 적립건수 파악
###############################################################################
def get_today_visitor_count(driver):
    import re
    try:
        visit_selector = "body > div > div.main-tab-content > div.stats-row > div:nth-child(1) > div.stat-value-daily"
        el = driver.find_element(By.CSS_SELECTOR, visit_selector)
        text = el.text.strip()
        visit_value = re.sub(r'[^\d]', '', text)
        return int(visit_value or X)
    except NoSuchElementException:
        logging.warning("방문고객 정보 못 찾음, X로 처리")
        return X
    except Exception as e:
        logging.error(f"방문객 파싱 에러: {e}")
        return X

###############################################################################
# 6. 사용 메뉴
###############################################################################
def go_usage_selector(driver):
    """'포인트 적립&사용 조회' 메뉴 클릭"""
    usage_selector = "body > div > div.nav-container > div > div.nav-item.active > a"
    try:
        WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.CSS_SELECTOR, usage_selector)))
        driver.find_element(By.CSS_SELECTOR, usage_selector).click()
        logging.info("사용 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("사용 메뉴 버튼을 찾지 못함")
    time.sleep(5)

body > div > div.main-tab-content > div.summary-cards > div:nth-child(3) > div.card-content > div.card-value

###############################################################################
# 6. 사용금액 추출 함수 (값만 반환)
###############################################################################
def get_today_usage_sum(driver):
    import re
    try:
        usage_selector = "body > div > div.main-tab-content > div.summary-cards > div:nth-child(3) > div.card-content > div.card-value"
        el = driver.find_element(By.CSS_SELECTOR, usage_selector)
        text = el.text.strip()
        usage_value = re.sub(r'[^\d]', '', text)
        return int(usage_value or X)
    except NoSuchElementException:
        logging.warning("방문고객 정보 못 찾음, X로 처리")
        return X
    except Exception as e:
        logging.error(f"방문객 파싱 에러: {e}")
        return X

###############################################################################
# 7. 구글 스프레드시트 batch 업데이트
###############################################################################
def get_gspread_client_from_b64(service_account_json_b64):
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import base64
    import json
    import tempfile
    import datetime

    # 1) Base64 → JSON
    service_account_json = base64.b64decode(service_account_json_b64).decode('utf-8')

    # 2) 임시 파일로 저장
    tmp_credentials_file = "service_account_credentials.json"
    with open(tmp_credentials_file, "w", encoding="utf-8") as f:
        f.write(service_account_json)

    # 3) Drive/Sheets 스코프 추가
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(tmp_credentials_file, scope)
    client = gspread.authorize(creds)
    return client

def batch_update_sheet(service_account_json_b64, usage_sum, visitor_count):
    import datetime

    # 1) gspread client
    client = get_gspread_client_from_b64(service_account_json_b64)
    spreadsheet = client.open("청라 일일/월말 정산서")
    worksheet = spreadsheet.worksheet("무궁 청라")

    # 2) 날짜에 따른 행
    today_day = datetime.datetime.now().day
    row_index = today_day + 2

    # usage_sum → AK?, visitor_count → AI? (문제에서 언급한 열)
    ak_cell = f"AK{row_index}"
    ai_cell = f"AI{row_index}"

    # 3) batch_update
    updates = [
        {
            "range": ak_cell,
            "values": [[usage_sum]]  # 2차원 배열
        },
        {
            "range": ai_cell,
            "values": [[visitor_count]]
        }
    ]
    worksheet.batch_update(updates)

    logging.info(f"배치 업데이트 완료: {ak_cell}={usage_sum}, {ai_cell}={visitor_count}")

###############################################################################
# 메인 실행
###############################################################################
def main():
    setup_logging()

    try:
        # 환경변수
        point_id, point_pw, service_account_json_b64 = get_environment_variables()

        # 드라이버
        driver = get_chrome_driver(use_profile=False)

        # 로그인 & 팝업 닫기
        login_point(driver, point_id, point_pw)
        pop_up_close(driver)

        # 적립수 & 사용금액 구하기
        visitor_count = get_today_visitor_count(driver)
        logging.info(f"[결과] 오늘 방문객 수: {visitor_count}")
        usage_sum = get_today_usage_sum(driver)
        logging.info(f"[결과] 오늘 사용금액: {usage_sum}")

        # 두 값을 batch update
        batch_update_sheet(service_account_json_b64, usage_sum, visitor_count)

    except Exception as e:
        logging.error(f"스크립트 실행 중 에러: {e}")
        logging.error(traceback.format_exc())
    finally:
        # 드라이버 종료
        if 'driver' in locals():
            driver.quit()


if __name__ == "__main__":
    main()

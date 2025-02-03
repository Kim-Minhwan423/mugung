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

# Google Sheets (gspread, oauth2client)
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
      - CHENGLA_DODO_ID (도도 아이디)
      - CHENGLA_DODO_PW (도도 비밀번호)
      - SERVICE_ACCOUNT_JSON_BASE64 (Base64 인코딩된 Google Service Account JSON)
    """
    dodo_id = os.getenv("CHENGLA_DODO_ID")
    dodo_pw = os.getenv("CHENGLA_DODO_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not dodo_id or not dodo_pw:
        raise ValueError("CHENGLA_DODO_ID 혹은 CHENGLA_DODO_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    return dodo_id, dodo_pw, service_account_json_b64

###############################################################################
# 3. Chrome 드라이버 세팅
###############################################################################
def get_chrome_driver(use_profile=False):
    chrome_options = webdriver.ChromeOptions()
    #chrome_options.add_argument("--headless")  # 필요시 주석 해제

    # User-Agent 변경
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/110.0.5481.77 Safari/537.36"
    )

    if use_profile:
        unique_id = uuid.uuid4()
        user_data_dir = os.path.join(tempfile.gettempdir(), f"chrome_profile_{unique_id}")
        os.makedirs(user_data_dir, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        logging.info(f"[use_profile={use_profile}] 고유 Chrome 프로필 경로: {user_data_dir}")

    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1200,700")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # 웹드라이버 탐지 방지 스크립트
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        }
    )
    logging.info("ChromeDriver 초기화 성공")
    return driver

###############################################################################
# 4. 도도 로그인 및 페이지 이동
###############################################################################
def login_dodo(driver, dodo_id, dodo_pw):
    # 로그인 페이지 진입
    driver.get("https://manager.dodopoint.com")
    logging.info("도도 포인트 매니저 사이트 로그인 페이지 접속 완료")

    id_selector = "#email"
    pw_selector = "#password"
    login_btn_selector = "#login-form > div.login-form-footer > button"

    try:
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, id_selector)))
        driver.find_element(By.CSS_SELECTOR, id_selector).send_keys(dodo_id)
        logging.info("아이디 입력")
        driver.find_element(By.CSS_SELECTOR, pw_selector).send_keys(dodo_pw)
        logging.info("비밀번호 입력")
        driver.find_element(By.CSS_SELECTOR, login_btn_selector).click()
        logging.info("로그인 버튼 클릭")
    except TimeoutException:
        logging.warning("로그인 페이지 로딩 Timeout")
    time.sleep(5)

def submit(driver):
    submit_selector = "body > div > div > div > div:nth-child(2) > form > div > button"
    try:
        submit_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, submit_selector))
        )
        submit_btn.click()
        logging.info("팝업 닫기 완료")
    except TimeoutException:
        logging.info("팝업이 나타나지 않음(혹은 이미 닫힘)")
    except Exception as e:
        logging.warning(f"팝업 닫기 중 예외 발생: {e}")
    time.sleep(5)
    
def go_usage_selector(driver):
    usage_selector = "#root > div > div > div.page_271am > div.content_3Ng3n > div > div.flex-column_1Bf1I > div > ul > li:nth-child(3)"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, usage_selector)))
        driver.find_element(By.CSS_SELECTOR, usage_selector).click()
        logging.info("사용 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("사용 메뉴 버튼을 찾지 못함")
    time.sleep(5)



    
def go_report_selector(driver):
    report_selector = "#root > div > div > div.sidebar_1aM4U > div.sidebar-links_3_XgU > div.link_10seQ.active_3lR3D"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, report_selector)))
        driver.find_element(By.CSS_SELECTOR, report_selector).click()
        logging.info("분석 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("분석 메뉴 버튼을 찾지 못함")
    time.sleep(5)

def open_anal_selector(driver):
    anal_selector = "#root > div > div > div.page_271am > div.content_3Ng3n > div > div.menu_33KxA > div > div:nth-child(2) > div.name_3JWH7.open_DKP_g > i > svg"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, anal_selector)))
        driver.find_element(By.CSS_SELECTOR, anal_selector).click()
        logging.info("방문 분석 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("방문 분석 메뉴 버튼을 찾지 못함")
    time.sleep(1)

def go_visit_selector(driver):
    visit_selector = "#root > div > div > div.page_271am > div.content_3Ng3n > div > div.menu_33KxA > div > div:nth-child(2) > div:nth-child(2) > div:nth-child(1)"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, visit_selector)))
        driver.find_element(By.CSS_SELECTOR, visit_selector).click()
        logging.info("방문 현황 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("방문 현황 메뉴 버튼을 찾지 못함")
    time.sleep(5)

def go_today_selector(driver):
    today_selector = "#root > div > div > div.page_271am > div.content_3Ng3n > div > div.page_2JdUB > div.date-range-filter_cI11I > div.btn-group_iydkX.quick-filter_2rcfW > div:nth-child(1)"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, today_selector)))
        driver.find_element(By.CSS_SELECTOR, today_selector).click()
        logging.info("오늘 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("오늘 메뉴 버튼을 찾지 못함")
    time.sleep(5)

def check_and_update_today_visit(driver, service_account_json_b64)
    try:
        today_visit_xpath = ("//*[@id='root']/div/div/div[2]/div[2]/div/div[2]/div[2]/div[1]/div[2]/text()")
        today_visit_text = driver.find_element(By.XPATH, today_visit_xpath).text.strip()
        today_visit_amount = today_visit_text.replace(",", "")  # 콤마 제거 등 전처리
        logging.info(f"방문고객 텍스트: {today_visit_text} → 파싱 결과: {today_visit_amount}")

        # 구글 시트에 업데이트
        update_today_visit_in_google_sheet(service_account_json_b64, today_visit_amount)
except NoSuchElementException:
     logging.warning("방문고객 정보를 찾을 수 없습니다.")
except Exception as e:
     logging.error(f"방문고객 추출/업데이트 중 에러 발생: {e}")
     logging.error(traceback.format_exc())
      
###############################################################################
# 구글 시트 업데이트 함수
###############################################################################
def update_today_visit_in_google_sheet(service_account_json_b64, today_visit_amount):
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import base64
    import datetime
    
    # Base64 인코딩 된 서비스 계정 JSON 복원
    service_account_json = base64.b64decode(service_account_json_b64).decode('utf-8')
    
    # 임시 파일에 JSON 저장
    tmp_credentials_file = "service_account_credentials.json"
    with open(tmp_credentials_file, "w", encoding="utf-8") as f:
        f.write(service_account_json)
    
    # 구글 스프레드 시트 인증
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(tmp_credentials_file, scope)
    client = gspread.authorize(creds)

    # 스프레드시트와 시트 선택 (이름은 실제 환경에 맞게 수정)
    spreadsheet = client.open("청라 일일/월말 정산서")
    worksheet = spreadsheet.worksheet("무궁 청라")

    # 오늘 일(day)에 해당하는 행에 방문고객 기입
    today_day = datetime.datetime.now().day
    row_to_update = today_day + 2  # 예: 1일 -> 3행, 2일 -> 4행 ...
    cell_to_update = f"AI{row_to_update}"

    worksheet.update_acell(cell_to_update, today_visit_amount)
    logging.info(f"{cell_to_update} 셀에 사용금액({today_visit_amount}) 업데이트 완료")

###############################################################################
# 메인 실행 부분
###############################################################################
def main():
    setup_logging()

    try:
        dodo_id, dodo_pw, service_account_json_b64 = get_environment_variables()
        driver = get_chrome_driver(use_profile=False)

        login_dodo(driver, dodo_id, dodo_pw)
        submit(driver)            # 팝업 닫기 시도
        go_report_selector(driver) # '분석' 메뉴로 이동
        open_anal_selector(driver) # '방문 분석' 메뉴로 이동
        go_visit_selector(driver) # '방문 현황' 메뉴로 이동
        go_today_selector(driver) # '오늘' 메뉴로 이동

        # 방문고객 수 체크 & 구글 시트 업데이트
        check_and_update_today_visit(driver, service_account_json_b64)

    except Exception as e:
        logging.error(f"스크립트 실행 중 에러 발생: {e}")
        logging.error(traceback.format_exc())
    finally:
        # 작업 종료 후 드라이버 종료
        if 'driver' in locals():
            driver.quit()

if __name__ == "__main__":
    main()

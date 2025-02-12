import os
import sys
import time
import datetime
import logging
import traceback
import base64
import json

# Selenium
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
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
# 2. 환경 변수 불러오기 (NAVER + GOOGLE SHEETS)
###############################################################################
def get_environment_variables():
    naver_id = os.getenv("NAVER_ID")
    naver_pw = os.getenv("NAVER_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not naver_id or not naver_pw:
        raise ValueError("NAVER_ID 혹은 NAVER_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    return naver_id, naver_pw, service_account_json_b64

###############################################################################
# 3. Chrome 드라이버 설정
###############################################################################
def get_chrome_driver():
    chrome_options = webdriver.ChromeOptions()
    #chrome_options.add_argument("--headless")  # 화면 없이 실행하려면 활성화

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
    chrome_options.add_argument("--window-size=1280,960")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """
        }
    )

    logging.info("ChromeDriver 초기화 성공")
    return driver

###############################################################################
# 4. 네이버 로그인 (CSS 선택자 수정)
###############################################################################
def login_naver(driver, user_id, password):
    driver.get("https://www.naver.com")
    logging.info("네이버 페이지 접속 완료")
    time.sleep(3)

    try:
        # ✅ 로그인 버튼 클릭 (수정된 선택자 사용)
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, f"//*[@id='account']/div/a"))
        )
        login_button.click()
        logging.info("로그인 버튼 클릭")
        time.sleep(5)  

        # ✅ 아이디 입력
        username_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#id"))
        )
        username_input.click()
        username_input.send_keys(user_id)
        logging.info("아이디 입력 완료")
        time.sleep(1)

        # ✅ 비밀번호 입력
        password_input = driver.find_element(By.CSS_SELECTOR, "#pw")
        password_input.click()
        password_input.send_keys(password)
        logging.info("비밀번호 입력 완료")
        time.sleep(1)

        # ✅ 로그인 버튼 클릭 (이스케이프 수정)
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, r"#log\.login"))
        )
        login_button.click()
        logging.info("로그인 버튼 클릭")
        time.sleep(5)

    except Exception as e:
        logging.error(f"로그인 중 오류 발생: {e}")
        traceback.print_exc()

###############################################################################
# 5. Google Sheets 인증
###############################################################################
def get_gspread_client_from_b64(service_account_json_b64):
    json_data = base64.b64decode(service_account_json_b64).decode('utf-8')
    service_account_info = json.loads(json_data)

    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        service_account_info, 
        ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(credentials)

###############################################################################
# 6. Google Sheets 업데이트 (업데이트 시간 추가)
###############################################################################
def update_google_sheets(client):
    try:
        doc = client.open("청라 일일/월말 정산서")
        sheet = doc.worksheet("무궁 청라")

        # ✅ 업데이트 시간 기록
        sheet.update("A26", [["업데이트 완료", str(datetime.datetime.now())]])

        logging.info("Google Sheets 업데이트 완료")
    except Exception as e:
        logging.error(f"Google Sheets 업데이트 중 오류 발생: {e}")
        traceback.print_exc()

###############################################################################
# 7. 메인 실행 흐름
###############################################################################
def main():
    setup_logging('script.log')

    naver_id, naver_pw, service_account_json_b64 = get_environment_variables()
    driver = get_chrome_driver()

    try:
        # ✅ 네이버 로그인 (수정된 코드 적용)
        login_naver(driver, user_id=naver_id, password=naver_pw)
        driver.save_screenshot("full_screenshot.png")

        # ✅ Google Sheets 인증
        client = get_gspread_client_from_b64(service_account_json_b64)

        # ✅ Google Sheets 업데이트
        update_google_sheets(client)

    except Exception as e:
        logging.error(f"에러 발생: {e}")
        traceback.print_exc()

    finally:
        driver.quit()
        logging.info("WebDriver 종료")

if __name__ == "__main__":
    main()

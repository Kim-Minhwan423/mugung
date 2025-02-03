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
      - CHENGLA_DODO_ID
      - CHENGLA_DODO_PW
      - SERVICE_ACCOUNT_JSON_BASE64
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
    # 필요 시 무헤드리스 사용하려면 주석 해제
    chrome_options.add_argument("--headless")

    # User-Agent (원하시면 조정)
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
def login_dodo(driver, dodo_id, dodo_pw):
    driver.get("https://manager.dodopoint.com")
    logging.info("도도 포인트 매니저 로그인 페이지 접속 완료")

    id_selector = "#email"
    pw_selector = "#password"
    login_btn_selector = "#login-form > div.login-form-footer > button"

    try:
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, id_selector)))
        driver.find_element(By.CSS_SELECTOR, id_selector).send_keys(dodo_id)
        logging.info("아이디 입력 완료")
        driver.find_element(By.CSS_SELECTOR, pw_selector).send_keys(dodo_pw)
        logging.info("비밀번호 입력 완료")
        driver.find_element(By.CSS_SELECTOR, login_btn_selector).click()
        logging.info("로그인 버튼 클릭")
    except TimeoutException:
        logging.warning("로그인 페이지 로딩 Timeout")
    time.sleep(5)

def submit(driver):
    """첫 팝업 닫기"""
    submit_selector = "body > div > div > div > div:nth-child(2) > form > div > button"
    try:
        btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, submit_selector)))
        btn.click()
        logging.info("기본 팝업 닫기")
    except TimeoutException:
        logging.info("팝업이 없거나 이미 닫힘 (submit)")
    except Exception as e:
        logging.warning(f"팝업 닫기 중 예외: {e}")
    time.sleep(5)

def pop_up_close(driver):
    """추가 팝업1 닫기"""
    pop_up_close_selector = (
        "#root > div > div > div.page_271am > div.header_10whZ > "
        "div.right-grp_gMFbo > div:nth-child(1) > div.speech-bubble-wrapper_1kB-H > "
        "div.speech-bubble_bq6wO > div > div.button-container_2DZwH > div"
    )
    try:
        btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, pop_up_close_selector)))
        btn.click()
        logging.info("팝업 닫기 (pop_up_close)")
    except TimeoutException:
        logging.info("팝업1 없음(또는 이미 닫힘)")
    except Exception as e:
        logging.warning(f"팝업 닫기 중 예외: {e}")
    time.sleep(5)

def pop_up_close_2(driver):
    """추가 팝업2 닫기"""
    pop_up_close_2_selector = "body > div:nth-child(15) > div > div.header_Lt14v > div > button"
    try:
        btn2 = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, pop_up_close_2_selector)))
        btn2.click()
        logging.info("팝업 닫기 (pop_up_close_2)")
    except TimeoutException:
        logging.info("팝업2 없음(또는 이미 닫힘)")
    except Exception as e:
        logging.warning(f"팝업2 닫기 예외: {e}")
    time.sleep(5)

###############################################################################
# 5. 사용 메뉴 & 방문 메뉴
###############################################################################
def go_usage_selector(driver):
    """'사용' 메뉴 클릭"""
    usage_selector = "#root > div > div > div.page_271am > div.content_3Ng3n > div > div.flex-column_1Bf1I > div > ul > li:nth-child(3)"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, usage_selector)))
        driver.find_element(By.CSS_SELECTOR, usage_selector).click()
        logging.info("사용 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("사용 메뉴 버튼을 찾지 못함")
    time.sleep(5)

def go_report_selector(driver):
    """'분석' 메뉴"""
    report_selector = "#root > div > div > div.sidebar_1aM4U > div.sidebar-links_3_XgU > div:nth-child(4) > i"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, report_selector)))
        driver.find_element(By.CSS_SELECTOR, report_selector).click()
        logging.info("분석 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("분석 메뉴 버튼 못찾음")
    time.sleep(5)

def open_anal_selector(driver):
    """'방문 분석' 메뉴 열기"""
    anal_selector = "#root > div > div > div.page_271am > div.content_3Ng3n > div > div.menu_33KxA > div > div:nth-child(2)"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, anal_selector)))
        driver.find_element(By.CSS_SELECTOR, anal_selector).click()
        logging.info("방문 분석 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("방문 분석 메뉴 버튼 못찾음")
    time.sleep(5)

def go_visit_selector(driver):
    """'방문 현황' 버튼"""
    visit_selector = "#root > div > div > div.page_271am > div.content_3Ng3n > div > div.menu_33KxA > div > div:nth-child(2) > div:nth-child(2) > div:nth-child(1)"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, visit_selector)))
        driver.find_element(By.CSS_SELECTOR, visit_selector).click()
        logging.info("방문 현황 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("방문 현황 메뉴 버튼 못찾음")
    time.sleep(5)

def go_today_selector(driver):
    """'오늘' 버튼"""
    today_selector = "#root > div > div > div.page_271am > div.content_3Ng3n > div > div.page_2JdUB > div.date-range-filter_cI11I > div.btn-group_iydkX.quick-filter_2rcfW > div:nth-child(1)"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, today_selector)))
        driver.find_element(By.CSS_SELECTOR, today_selector).click()
        logging.info("오늘 메뉴 진입 버튼 클릭")
    except TimeoutException:
        logging.warning("오늘 메뉴 버튼 못찾음")
    time.sleep(5)

###############################################################################
# 6. 사용금액/방문객 추출 함수 (값만 반환)
###############################################################################
def get_today_usage_sum(driver):
    """
    1) 첫 날짜가 오늘인지 확인
    2) i=3부터 다음 '날짜' 블록 전까지 사용금액 누적
    3) 사용금액(정수) 반환
       (못 찾으면 0)
    """
    import re
    import datetime

    try:
        first_date_xpath = '//*[@id="root"]/div/div/div[2]/div[2]/div/div[1]/div/div[1]/div/div[2]'
        first_date_text = driver.find_element(By.XPATH, first_date_xpath).text.strip()
    except NoSuchElementException:
        logging.warning("처음 날짜 블록(2) 못 찾음")
        return 0
    
    today_str = datetime.datetime.now().strftime("%Y.%m.%d")
    if first_date_text != today_str:
        logging.info(f"첫 날짜({first_date_text}) != 오늘({today_str}), usage=0")
        return 0
    
    usage_sum = 0
    for i in range(3, 20):
        date_candidate_xpath = f'//*[@id="root"]/div/div/div[2]/div[2]/div/div[1]/div/div[1]/div/div[{i}]'
        try:
            block_text = driver.find_element(By.XPATH, date_candidate_xpath).text.strip()
            # 날짜 패턴이라면 중단
            if re.match(r'^\d{4}\.\d{2}\.\d{2}$', block_text):
                break

            usage_xpath = date_candidate_xpath + '/div[2]/span[1]/span/b'
            usage_text = driver.find_element(By.XPATH, usage_xpath).text.strip()
            usage_value = re.sub(r'[^\d]', '', usage_text)
            usage_sum += int(usage_value or 0)
        except NoSuchElementException:
            break
        except Exception as e:
            logging.warning(f"사용금액 파싱 예외: {e}")
            break
    
    return usage_sum

def get_today_visitor_count(driver):
    """
    방문객 수(정수) 반환
    (없으면 0)
    """
    import re
    try:
        visit_xpath = "//*[@id='root']/div/div/div[2]/div[2]/div/div[2]/div[2]/div[1]/div[2]"
        el = driver.find_element(By.XPATH, visit_xpath)
        text = el.text.strip()
        visit_value = re.sub(r'[^\d]', '', text)
        return int(visit_value or 0)
    except NoSuchElementException:
        logging.warning("방문고객 정보 못 찾음, 0으로 처리")
        return 0
    except Exception as e:
        logging.error(f"방문객 파싱 에러: {e}")
        return 0

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
        dodo_id, dodo_pw, service_account_json_b64 = get_environment_variables()

        # 드라이버
        driver = get_chrome_driver(use_profile=False)

        # 로그인 & 팝업 닫기
        login_dodo(driver, dodo_id, dodo_pw)
        submit(driver)
        pop_up_close(driver)
        pop_up_close_2(driver)

        # '사용' 메뉴 → 오늘 사용금액 구하기
        go_usage_selector(driver)
        usage_sum = get_today_usage_sum(driver)
        logging.info(f"[결과] 오늘 사용금액: {usage_sum}")

        # '분석' → '방문 현황' → '오늘' → 방문객 수
        go_report_selector(driver)
        open_anal_selector(driver)
        go_visit_selector(driver)
        go_today_selector(driver)
        visitor_count = get_today_visitor_count(driver)
        logging.info(f"[결과] 오늘 방문객 수: {visitor_count}")

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

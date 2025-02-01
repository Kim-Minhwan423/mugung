import os
import sys
import re
import time
import datetime
import logging
import traceback
import base64
import json
import uuid        # [추가]
import tempfile    # [추가]

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
# 1. 로깅 설정 (예시)
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
# 2. (예) 환경 변수 불러오기
###############################################################################
def get_environment_variables():
    """
    필수 환경 변수:
        - YOGIYO_ID (요기요 아이디)
        - YOGIYO_PW (요기요 비밀번호)
        - SERVICE_ACCOUNT_JSON_BASE64 (Base64 인코딩된 Google Service Account JSON)
    """
    yogiyo_id = os.getenv("YOGIYO_ID")
    yogiyo_pw = os.getenv("YOGIYO_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    # 실제 운영 시, 아래처럼 값이 없으면 에러를 내주세요.
    if not yogiyo_id or not yogiyo_pw:
        raise ValueError("YOGIYO_ID 혹은 YOGIYO_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    return yogiyo_id, yogiyo_pw, service_account_json_b64


###############################################################################
# 3. Chrome 드라이버 세팅 (고유 경로 프로필 사용 예시)
###############################################################################
def get_chrome_driver(use_profile=False):
    """
    ChromeDriver 설정
    """
    chrome_options = webdriver.ChromeOptions()
    #chrome_options.add_argument("--headless")  # 필요 시 활성화

    # User-Agent 변경
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/110.0.5481.77 Safari/537.36"
    )

    if use_profile:
        # 매 실행마다 임시폴더에 고유 폴더 생성
        unique_id = uuid.uuid4()
        user_data_dir = os.path.join(tempfile.gettempdir(), f"chrome_profile_{unique_id}")
        os.makedirs(user_data_dir, exist_ok=True)

        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        # 예: chrome_options.add_argument("--profile-directory=Default")
        logging.info(f"[use_profile=True] 고유 Chrome 프로필 경로: {user_data_dir}")

    # 일반 옵션들
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1029,657")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # 웹드라이버 티 안 나게
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
# 4. 요기요 로그인 → 팝업 닫기 → 셀프서비스 → 주문내역 진입
###############################################################################
def login_yogiyo(driver, yogiyo_id, yogiyo_pw):
    """
    1) https://ceo.yogiyo.co.kr/self-service-home/
    2) id, pw 입력
    3) 로그인 버튼
    """
    driver.get("https://ceo.yogiyo.co.kr/self-service-home/")
    logging.info("요기요 사장님 사이트 로그인 페이지 접속 완료")

    # 아이디 입력
    id_selector = "#root > div > div.LoginLayout__Container-sc-1dkvjmn-1.cFYxDO > div > div.Login__Container-sc-11eppm3-0.hruuNe > form > div:nth-child(1) > div > div.sc-fEOsli.iqThlJ > div.sc-bjUoiL.LLOzV > input"
    pw_selector = "#root > div > div.LoginLayout__Container-sc-1dkvjmn-1.cFYxDO > div > div.Login__Container-sc-11eppm3-0.hruuNe > form > div:nth-child(2) > div > div.sc-fEOsli.iqThlJ > div.sc-bjUoiL.LLOzV > input"
    login_btn_selector = "#root > div > div.LoginLayout__Container-sc-1dkvjmn-1.cFYxDO > div > div.Login__Container-sc-11eppm3-0.hruuNe > form > button"

    try:
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, id_selector)))
        driver.find_element(By.CSS_SELECTOR, id_selector).send_keys(yogiyo_id)
        logging.info("아이디 입력")

        driver.find_element(By.CSS_SELECTOR, pw_selector).send_keys(yogiyo_pw)
        logging.info("비밀번호 입력")

        # 로그인 버튼 클릭
        driver.find_element(By.CSS_SELECTOR, login_btn_selector).click()
        logging.info("로그인 버튼 클릭")
    except TimeoutException:
        logging.warning("로그인 페이지 로딩 Timeout")

    time.sleep(5)  # 로그인 처리 대기


def close_popup_if_exist(driver):
    """
    로그인 후 뜨는 팝업(#portal-root 등등) 닫기
    예시 CSS: #portal-root > div > ...
    """
    popup_close_selector = "#portal-root > div > div > div.FullScreenModal__Header-sc-7lyzl-1.eQqjUi > svg"
    try:
        close_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, popup_close_selector))
        )
        close_btn.click()
        logging.info("팝업 닫기 완료")
    except TimeoutException:
        logging.info("팝업이 나타나지 않음(혹은 이미 닫힘)")

def go_order_history(driver):
    """
    주문내역 메뉴 클릭
    """
    order_btn_selector = "#root > div > div.CommonLayout__UnderHeader-sc-f8yrrc-2.feAuQx "
    "> div.LNB__Container-sc-1eyat45-17.gDEqtO.LNB__StyledLNB-sc-1eyat45-19.PQgEK > div.LNB__ScrollWrapper-sc-1eyat45-16.fHssYu "
    "> div.LNB__QuickMenu-sc-1eyat45-2.hGHFDR > button.LNB__MenuButton-sc-1eyat45-3.flLQfy"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, order_btn_selector)))
        driver.find_element(By.CSS_SELECTOR, order_btn_selector).click()
        logging.info("주문내역 버튼 클릭")
    except TimeoutException:
        logging.warning("주문내역 버튼을 찾지 못함")

    time.sleep(3)  # 주문내역 화면 로딩 대기

def select_daily_range(driver):
    """
    날짜 필드 클릭 → '일별' shortcut 선택
    """
    date_field_selector = ("#common-layout-wrapper-id > div.CommonLayout__Contents-sc-f8yrrc-1.fWTDpk > div > div > div.CardListLayout__CardListContainer-sc-26whdp-0.jofZaF.CardListLayout__StyledCardListLayout-sc-26whdp-1.lgKFYo > div > div.TitleContentCard__CardContentLayout-sc-1so7oge-0.fwXwFk > div > div > div > div.OrderHistory__FilterContainer-sc-1ccqzi9-4.kpcocB > div > div.DateRangePicker__Container-sc-1kvmudn-0.iLbmAj.OrderHistory__StyledDateRangePicker-sc-1ccqzi9-7.cTvWxw > div > div > div > div > div.CustomTextField__Right-sc-1m4c99t-3.iVfYjE > div > svg > g > rect")
    try:
        # 날짜 필드 클릭
        date_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, date_field_selector))
        )
        date_field.click()
        logging.info("날짜 필드 클릭")
        time.sleep(1)

        # 팝업에서 '일별' 버튼 클릭 (예시 셀렉터)
        daily_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "#common-layout-wrapper-id > div.CommonLayout__Contents-sc-f8yrrc-1.fWTDpk > div > div "
                "> div.CardListLayout__CardListContainer-sc-26whdp-0.jofZaF.CardListLayout__StyledCardListLayout-sc-26whdp-1.lgKFYo "
                "> div > div.TitleContentCard__CardContentLayout-sc-1so7oge-0.fwXwFk > div > div > div "
                "> div.OrderHistory__FilterContainer-sc-1ccqzi9-4.kpcocB > div "
                "> div.DateRangePicker__Container-sc-1kvmudn-0.iLbmAj.OrderHistory__StyledDateRangePicker-sc-1ccqzi9-7.cTvWxw "
                "> div.react-datepicker__tab-loop > div.react-datepicker-popper.custom-popper > div > div "
                "> div.getCustomCalendarCotainer__OptionBox-sc-1tsrb16-3.eBJNps > div.getCustomCalendarCotainer__ShortcutList-sc-1tsrb16-0.UPVGG > div:nth-child(2)"
            ))
        )
        daily_btn.click()
        logging.info("일별 shortcut 클릭")
    except TimeoutException:
        logging.warning("날짜 필드 or '일별' shortcut을 찾지 못함")


###############################################################################
# 메인 실행 흐름 예시
###############################################################################
def main():
    setup_logging("script.log")

    # 환경 변수(아이디/비번) 가져오기
    yogiyo_id, yogiyo_pw, service_account_json_b64 = get_environment_variables()

    # use_profile=True 로 하면 고유 경로 프로필을 생성해 사용
    driver = get_chrome_driver(use_profile=True)

    try:
        # 1) 로그인
        login_yogiyo(driver, yogiyo_id, yogiyo_pw)

        # 2) 팝업 닫기
        close_popup_if_exist(driver)

        # 3) 주문내역 진입
        go_order_history(driver)

        # 4) 날짜 필드 클릭 → '일별' shortcut
        select_daily_range(driver)

        # TODO: 여기서 날짜를 세부적으로 설정하거나, 주문 목록을 스크래핑 등등
        # ...

    except Exception as e:
        logging.error(f"에러 발생: {e}")
        traceback.print_exc()
    finally:
        driver.quit()
        logging.info("WebDriver 종료")


if __name__ == "__main__":
    main()

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

    # 중복 핸들러 방지
    if logger.handlers:
        logger.handlers.clear()

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
    point_id = os.getenv("SONGDO_POINT_ID")
    point_pw = os.getenv("SONGDO_POINT_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not point_id or not point_pw:
        raise ValueError(
            "SONGDO_POINT_ID 혹은 SONGDO_POINT_PW 환경변수가 설정되지 않았습니다."
        )

    if not service_account_json_b64:
        raise ValueError(
            "SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다."
        )

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

    driver = webdriver.Chrome(
        service=service,
        options=chrome_options
    )

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(
                    navigator,
                    'webdriver',
                    {
                        get: () => undefined
                    }
                );
            """
        }
    )

    logging.info("ChromeDriver 초기화 성공")

    return driver


###############################################################################
# 4. 로그인 및 팝업 닫기
###############################################################################
def login_point(driver, point_id, point_pw):

    driver.get(
        "https://xn--3j1b74x8mfjtk.com/visits/stats/549"
    )

    logging.info("포인트 로그인 페이지 접속 완료")

    id_selector = "#mid"
    pw_selector = "#password"

    login_btn_selector = (
        "body > div.mx-auto.flex.min-h-screen.w-full.max-w-sm."
        "items-center > div > div:nth-child(2) > form > button"
    )

    try:

        WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, id_selector)
            )
        )

        driver.find_element(
            By.CSS_SELECTOR,
            id_selector
        ).send_keys(point_id)

        logging.info("아이디 입력 완료")

        driver.find_element(
            By.CSS_SELECTOR,
            pw_selector
        ).send_keys(point_pw)

        logging.info("비밀번호 입력 완료")

        driver.find_element(
            By.CSS_SELECTOR,
            login_btn_selector
        ).click()

        logging.info("로그인 버튼 클릭")

    except TimeoutException:
        logging.warning("로그인 페이지 로딩 Timeout")

    # 로그인 후 통계 페이지 로딩 대기
    #
    # 사용금액 카드가 실제 DOM에 생성될 때까지 기다립니다.
    usage_xpath = (
        "/html/body/div[2]/div/div/section/"
        "div[2]/div[8]/div/div/div/div[2]"
    )

    try:

        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.XPATH, usage_xpath)
            )
        )

        logging.info("포인트 통계 페이지 로딩 완료")

    except TimeoutException:

        logging.warning(
            "포인트 통계 페이지 로딩 대기 Timeout"
        )

        # 혹시 React 렌더링이 조금 늦는 경우를 대비
        time.sleep(3)


###############################################################################
# 5. 오늘 사용금액 조회
###############################################################################
def get_today_usage(driver):

    # -----------------------------------
    # 실제 페이지에서 확인한 CSS Selector
    # -----------------------------------
    usage_css_selector = (
        "body > div.min-h-screen.w-full.bg-muted\\/30 > "
        "div > div > section > "
        "div.grid.grid-cols-2.gap-4.md\\:grid-cols-4 > "
        "div:nth-child(8) > div > div > div > "
        "div.mt-1.text-2xl.font-bold"
    )

    # -----------------------------------
    # 실제 페이지에서 확인한 XPath
    # -----------------------------------
    usage_xpath = (
        "/html/body/div[2]/div/div/section/"
        "div[2]/div[8]/div/div/div/div[2]"
    )

    # =========================================================================
    # 1차 - CSS Selector
    # =========================================================================
    try:

        logging.info(
            "오늘 사용금액 조회 시작 - CSS Selector"
        )

        element = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located(
                (
                    By.CSS_SELECTOR,
                    usage_css_selector
                )
            )
        )

        text = element.text.strip()

        logging.info(
            f"[디버그] CSS 사용금액 원본 텍스트: '{text}'"
        )

        usage_value = re.sub(
            r'[^\d]',
            '',
            text
        )

        if usage_value:

            logging.info(
                f"오늘 사용금액: {usage_value}"
            )

            return int(usage_value)

    except Exception as e:

        logging.warning(
            f"CSS Selector 사용금액 조회 실패: {e}"
        )

    # =========================================================================
    # 2차 - XPath
    # =========================================================================
    try:

        logging.info(
            "오늘 사용금액 조회 시작 - XPath"
        )

        element = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    usage_xpath
                )
            )
        )

        text = element.text.strip()

        logging.info(
            f"[디버그] XPath 사용금액 원본 텍스트: '{text}'"
        )

        usage_value = re.sub(
            r'[^\d]',
            '',
            text
        )

        if usage_value:

            logging.info(
                f"오늘 사용금액: {usage_value}"
            )

            return int(usage_value)

    except Exception as e:

        logging.error(
            f"XPath 사용금액 파싱 오류: {e}"
        )

    # =========================================================================
    # 최종 실패
    # =========================================================================
    logging.error(
        "오늘 사용금액을 가져오지 못했습니다."
    )

    try:

        logging.error(
            f"[디버그] 현재 URL: {driver.current_url}"
        )

        logging.error(
            f"[디버그] 현재 페이지 제목: {driver.title}"
        )

    except Exception:
        pass

    return -1


###############################################################################
# 6. 오늘 적립건수
###############################################################################
def get_today_saved_count(driver):

    status_xpath = (
        "/html/body/div[2]/div/div/div[2]/section[1]/"
        "div[2]/div[1]/div/div/div/div[2]"
    )

    try:

        WebDriverWait(driver, 10).until(
            lambda d:
            d.find_element(
                By.XPATH,
                status_xpath
            ).text.strip() != ''
        )

        text = driver.find_element(
            By.XPATH,
            status_xpath
        ).text.strip()

        logging.info(
            f"[디버그] 적립건수 텍스트: '{text}'"
        )

        saved_count = int(
            re.sub(
                r'[^\d]',
                '',
                text
            )
        )

        logging.info(
            f"오늘 적립건수: {saved_count}"
        )

        return saved_count

    except Exception as e:

        logging.error(
            f"적립건수 파싱 오류: {e}"
        )

        return -1


###############################################################################
# 7. 평균 방문간격
###############################################################################
def get_average_visit_gap(driver):

    xpath = (
        "/html/body/div[2]/div/div/section/"
        "div[2]/div[3]/div/div/div/div[2]"
    )

    try:

        WebDriverWait(driver, 10).until(
            lambda d:
            d.find_element(
                By.XPATH,
                xpath
            ).text.strip() != ''
        )

        text = driver.find_element(
            By.XPATH,
            xpath
        ).text.strip()

        match = re.search(
            r'\d+(\.\d+)?',
            text
        )

        value = (
            float(match.group())
            if match
            else -1
        )

        logging.info(
            f"평균 방문간격: {value}"
        )

        return value

    except Exception as e:

        logging.error(
            f"평균 방문간격 파싱 오류: {e}"
        )

        return -1


###############################################################################
# 8. 최근 3개월 방문자수
###############################################################################
def get_recent_visit(driver):

    xpath = (
        "/html/body/div[2]/div/div/section/"
        "div[2]/div[2]/div/div/div/div[2]"
    )

    try:

        WebDriverWait(driver, 10).until(
            lambda d:
            d.find_element(
                By.XPATH,
                xpath
            ).text.strip() != ''
        )

        text = driver.find_element(
            By.XPATH,
            xpath
        ).text.strip()

        value = int(
            re.sub(
                r'[^\d]',
                '',
                text
            )
        )

        logging.info(
            f"최근 3개월 방문자수: {value}"
        )

        return value

    except Exception as e:

        logging.error(
            f"최근 방문 파싱 오류: {e}"
        )

        return -1


###############################################################################
# 9. 포인트 보유자 수
###############################################################################
def get_point_holder(driver):

    xpath = (
        "/html/body/div[2]/div/div/section/"
        "div[2]/div[7]/div/div/div/div[2]"
    )

    try:

        WebDriverWait(driver, 10).until(
            lambda d:
            d.find_element(
                By.XPATH,
                xpath
            ).text.strip() != ''
        )

        text = driver.find_element(
            By.XPATH,
            xpath
        ).text.strip()

        value = int(
            re.sub(
                r'[^\d]',
                '',
                text
            )
        )

        logging.info(
            f"포인트 보유자 수: {value}"
        )

        return value

    except Exception as e:

        logging.error(
            f"포인트 보유자 파싱 오류: {e}"
        )

        return -1


###############################################################################
# 10. Google Sheets 인증
###############################################################################
def get_gspread_client_from_b64(
    service_account_json_b64
):

    service_account_json = base64.b64decode(
        service_account_json_b64
    ).decode('utf-8')

    tmp_credentials_file = (
        "service_account_credentials.json"
    )

    with open(
        tmp_credentials_file,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            service_account_json
        )

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_name(
        tmp_credentials_file,
        scope
    )

    client = gspread.authorize(
        creds
    )

    return client


###############################################################################
# 11. Google Sheets 업데이트
###############################################################################
def batch_update_sheet(
    service_account_json_b64,
    usage_value,
    visitor_count,
    average_visit_gap,
    recent_visit,
    point_holder
):

    client = get_gspread_client_from_b64(
        service_account_json_b64
    )

    spreadsheet = client.open(
        "송도 일일/월말 정산서"
    )

    # -----------------------
    # 송도 시트
    # -----------------------
    songdo_ws = spreadsheet.worksheet(
        "송도"
    )

    today_day = datetime.datetime.now().day

    row_index = today_day + 2

    updates_songdo = [
        {
            "range": f"AK{row_index}",
            "values": [[usage_value]]
        },
        {
            "range": f"AI{row_index}",
            "values": [[visitor_count]]
        },
    ]

    songdo_ws.batch_update(
        updates_songdo
    )

    # -----------------------
    # 예약&마케팅 시트
    # -----------------------
    marketing_ws = spreadsheet.worksheet(
        "예약&마케팅"
    )

    updates_marketing = [
        {
            "range": "O42",
            "values": [[average_visit_gap]]
        },
        {
            "range": "K42",
            "values": [[recent_visit]]
        },
        {
            "range": "O41",
            "values": [[point_holder]]
        },
    ]

    marketing_ws.batch_update(
        updates_marketing
    )

    logging.info(
        f"업데이트 완료 | "
        f"사용금액:{usage_value}, "
        f"방문:{visitor_count}, "
        f"방문간격:{average_visit_gap}, "
        f"3개월:{recent_visit}, "
        f"보유자:{point_holder}"
    )


###############################################################################
# 12. 메인 실행
###############################################################################
def main():

    setup_logging()

    driver = None

    try:

        # 환경변수
        (
            point_id,
            point_pw,
            service_account_json_b64
        ) = get_environment_variables()

        # Chrome 실행
        driver = get_chrome_driver(
            use_profile=False
        )

        # 로그인
        login_point(
            driver,
            point_id,
            point_pw
        )

        # -----------------------------
        # 데이터 조회
        # -----------------------------
        usage_value = get_today_usage(
            driver
        )

        visitor_count = get_today_saved_count(
            driver
        )

        average_visit_gap = get_average_visit_gap(
            driver
        )

        recent_visit = get_recent_visit(
            driver
        )

        point_holder = get_point_holder(
            driver
        )

        # -----------------------------
        # Google Sheets 업데이트
        # -----------------------------
        batch_update_sheet(
            service_account_json_b64,
            usage_value,
            visitor_count,
            average_visit_gap,
            recent_visit,
            point_holder
        )

    except Exception as e:

        logging.error(
            f"스크립트 실행 중 에러: {e}"
        )

        logging.error(
            traceback.format_exc()
        )

    finally:

        if driver is not None:

            driver.quit()


###############################################################################
# 실행
###############################################################################
if __name__ == "__main__":
    main()

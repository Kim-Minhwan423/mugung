
import os
import sys
import time
import json
import base64
import logging

import gspread

from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
    StaleElementReferenceException
)

from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from webdriver_manager.chrome import ChromeDriverManager


###############################################################################
# 1. 로깅 설정
###############################################################################

def setup_logging(log_filename="script.log"):

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(
        logging.Formatter("%(message)s")
    )

    file_handler = logging.FileHandler(
        log_filename,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(message)s")
    )

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)


###############################################################################
# 2. 안전 클릭 함수
###############################################################################

def safe_click(driver, element):

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        element
    )

    time.sleep(0.2)

    try:
        element.click()

    except Exception:
        driver.execute_script(
            "arguments[0].click();",
            element
        )


def wait_and_click(driver, by, value, timeout=15):

    try:

        element = WebDriverWait(
            driver,
            timeout
        ).until(
            EC.element_to_be_clickable((by, value))
        )

        safe_click(driver, element)

        return True

    except Exception as e:

        logging.warning(
            f"일반 클릭 실패: {value} / {e}"
        )

        try:

            element = WebDriverWait(
                driver,
                5
            ).until(
                EC.presence_of_element_located((by, value))
            )

            driver.execute_script(
                "arguments[0].click();",
                element
            )

            return True

        except Exception as e2:

            logging.error(
                f"JavaScript 클릭 실패: {value} / {e2}"
            )

            return False


###############################################################################
# 3. 환경변수 설정
###############################################################################

def get_environment_variables():

    """
    필수 환경변수

    NAVER_ID
    NAVER_PW
    SERVICE_ACCOUNT_JSON_BASE64
    """

    naver_id = os.getenv("NAVER_ID")
    naver_pw = os.getenv("NAVER_PW")

    service_account_json_b64 = os.getenv(
        "SERVICE_ACCOUNT_JSON_BASE64"
    )

    if not naver_id or not naver_pw:

        raise ValueError(
            "NAVER_ID 또는 NAVER_PW 환경변수가 설정되지 않았습니다."
        )

    if not service_account_json_b64:

        raise ValueError(
            "SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다."
        )

    return (
        naver_id,
        naver_pw,
        service_account_json_b64
    )


###############################################################################
# 4. Selenium WebDriver 관리 클래스
###############################################################################

class SeleniumDriverManager:

    def __init__(self, headless=True, user_agent=None):

        self.headless = headless

        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/132.0.6834.110 Safari/537.36"
        )

        self.driver = None

    def __enter__(self):

        options = webdriver.ChromeOptions()

        #if self.headless:
         #   options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1180,980")
        options.add_argument(
            f"user-agent={self.user_agent}"
        )
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--lang=ko-KR")

        options.page_load_strategy = "eager"

        try:

            self.driver = webdriver.Chrome(
                service=Service(
                    ChromeDriverManager().install()
                ),
                options=options
            )

            self.driver.set_page_load_timeout(40)

            logging.info("WebDriver 초기화 성공")

        except WebDriverException as e:

            logging.error(
                f"WebDriver 초기화 실패: {e}"
            )

            raise

        return self.driver

    def __exit__(self, exc_type, exc_val, exc_tb):

        if self.driver:

            self.driver.quit()

            logging.info("WebDriver 종료")


###############################################################################
# 5. Google Sheets 관리 클래스
###############################################################################

class GoogleSheetsManager:

    def __init__(self, service_account_json_b64):

        self.service_account_json_b64 = (
            service_account_json_b64
        )

        self.client = None
        self.spreadsheet = None

    def authenticate(self):

        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        try:

            raw_json = base64.b64decode(
                self.service_account_json_b64
            ).decode("utf-8")

            creds_dict = json.loads(raw_json)

            creds = (
                ServiceAccountCredentials.from_json_keyfile_dict(
                    creds_dict,
                    scopes
                )
            )

            self.client = gspread.authorize(creds)

            logging.info("Google Sheets API 인증 성공")

        except Exception as e:

            logging.error(
                f"Google Sheets 인증 실패: {e}"
            )

            raise

    def open_spreadsheet(self, spreadsheet_name):

        if not self.client:

            raise RuntimeError(
                "Google API 인증이 선행되어야 합니다."
            )

        self.spreadsheet = self.client.open(
            spreadsheet_name
        )

        logging.info(
            f"스프레드시트 '{spreadsheet_name}' 열기 성공"
        )

    def get_worksheet(self, sheet_name):

        if not self.spreadsheet:

            raise RuntimeError(
                "스프레드시트를 먼저 열어야 합니다."
            )

        return self.spreadsheet.worksheet(sheet_name)


###############################################################################
# 6. 네이버 로그인 화면 진단
###############################################################################

def save_debug_files(driver):

    try:

        driver.save_screenshot(
            "naver_debug.png"
        )

        with open(
            "naver_debug.html",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(driver.page_source)

        logging.info("네이버 진단 파일 저장 완료")
        logging.info(f"현재 URL: {driver.current_url}")
        logging.info(f"페이지 제목: {driver.title}")

        links = driver.find_elements(
            By.TAG_NAME,
            "a"
        )

        for link in links[:30]:

            try:

                logging.info(
                    f"링크: {link.text} / "
                    f"{link.get_attribute('href')}"
                )

            except Exception:
                pass

    except Exception as e:

        logging.warning(
            f"진단 파일 저장 실패: {e}"
        )


###############################################################################
# 7. 네이버 스마트플레이스 로그인
###############################################################################

def naver_login(driver, naver_id, naver_pw):

    wait = WebDriverWait(driver, 20)

    logging.info("스마트플레이스 접속 시작")

    driver.get(
        "https://new.smartplace.naver.com/"
    )

    time.sleep(5)

    logging.info(
        f"현재 접속 URL: {driver.current_url}"
    )

    # 로그인 페이지 진입
    login_xpath = (
        '//*[@id="modal-root"]/div/header/div/div/div[1]/a'
    )

    login_clicked = wait_and_click(
        driver,
        By.XPATH,
        login_xpath,
        timeout=10
    )

    # 기존 XPath가 작동하지 않으면
    # 로그인 텍스트가 포함된 링크 탐색
    if not login_clicked:

        logging.warning(
            "기존 로그인 XPath 실패. 로그인 텍스트로 재검색"
        )

        login_text_xpath = (
            '//a[contains(normalize-space(.), "로그인")]'
        )

        login_clicked = wait_and_click(
            driver,
            By.XPATH,
            login_text_xpath,
            timeout=10
        )

    if not login_clicked:

        save_debug_files(driver)

        raise TimeoutException(
            "네이버 로그인 페이지 진입 버튼을 찾지 못했습니다."
        )

    logging.info("로그인 페이지 진입")

    # 아이디 입력
    id_input = wait.until(
        EC.presence_of_element_located(
            (By.ID, "id")
        )
    )

    id_input.clear()
    id_input.send_keys(naver_id)

    # 비밀번호 입력
    pw_input = wait.until(
        EC.presence_of_element_located(
            (By.ID, "pw")
        )
    )

    pw_input.clear()
    pw_input.send_keys(naver_pw)

    # 로그인 버튼 클릭
    login_button_clicked = wait_and_click(
        driver,
        By.ID,
        "loginBtn_row",
        timeout=15
    )

    if not login_button_clicked:

        save_debug_files(driver)

        raise TimeoutException(
            "네이버 로그인 버튼을 클릭하지 못했습니다."
        )

    logging.info("네이버 로그인 버튼 클릭 완료")

    time.sleep(5)

    logging.info(
        f"로그인 이후 URL: {driver.current_url}"
    )


###############################################################################
# 8. 예약·주문 탭 진입
###############################################################################

def enter_reservation_tab(driver):

    reservation_tab_xpath = (
        '//*[@id="modal-root"]/div/div/div/div/div/div[2]/ul/li[3]/a'
    )

    clicked = wait_and_click(
        driver,
        By.XPATH,
        reservation_tab_xpath,
        timeout=20
    )

    if not clicked:

        save_debug_files(driver)

        raise TimeoutException(
            "예약·주문 탭 진입 실패"
        )

    logging.info("예약·주문 탭 진입 완료")

    time.sleep(3)


###############################################################################
# 9. 송도점 예약관리 진입
###############################################################################

def enter_songdo_reservation(driver):

    songdo_button_xpath = (
        '//*[@id="modal-root"]/div/div/div/div/div[2]/div/div/'
        'ul/li[1]/div[2]/div/div[2]/div/button[1]'
    )

    clicked = wait_and_click(
        driver,
        By.XPATH,
        songdo_button_xpath,
        timeout=20
    )

    if not clicked:

        save_debug_files(driver)

        raise TimeoutException(
            "송도점 예약관리 버튼 클릭 실패"
        )

    logging.info("송도점 예약관리 진입 완료")

    time.sleep(3)


###############################################################################
# 10. 예약 정보 추출 함수
###############################################################################

def get_text(parent, xpath):

    try:

        element = parent.find_element(
            By.XPATH,
            xpath
        )

        return (
            element.get_attribute("innerText") or ""
        ).strip()

    except NoSuchElementException:

        return ""


###############################################################################
# 11. 예약 데이터 수집
###############################################################################

def collect_reservations(driver):

    reservation_container_xpath = (
        '//*[@id="app"]/div/div[2]/div[2]/div/div[3]/div[3]/div/div[2]'
    )

    wait = WebDriverWait(driver, 20)

    wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                reservation_container_xpath
            )
        )
    )

    time.sleep(3)

    reservation_xpath = (
        reservation_container_xpath + "/a"
    )

    reservation_elements = driver.find_elements(
        By.XPATH,
        reservation_xpath
    )

    total_count = len(reservation_elements)

    logging.info(
        f"현재 화면 예약 건수: {total_count}"
    )

    reservation_data = []

    for i in range(total_count):

        try:

            # 예약 요소 재조회
            reservations = driver.find_elements(
                By.XPATH,
                reservation_xpath
            )

            if i >= len(reservations):

                logging.warning(
                    f"{i + 1}번 예약 요소를 찾을 수 없습니다."
                )

                continue

            reservation = reservations[i]

            # 예약 상태
            status = get_text(
                reservation,
                "./div[2]"
            )

            # 날짜 및 시간
            date_time = get_text(
                reservation,
                "./div[6]/div/a/div[1]"
            )

            # 예약 인원
            people = get_text(
                reservation,
                "./div[6]/div/a/div[3]"
            )

            # 휴대폰 번호
            phone = get_text(
                reservation,
                "./div[4]"
            )

            # 예약 메뉴
            menu = get_text(
                reservation,
                "./div[6]/div/a/div[4]"
            )

            # 결제 금액
            payment = get_text(
                reservation,
                "./div[6]/div/a/div[7]"
            )

            row = [
                status,
                date_time,
                people,
                phone,
                menu,
                payment
            ]

            reservation_data.append(row)

            logging.info(
                f"[{i + 1}/{total_count}] "
                f"상태: {status} | "
                f"날짜: {date_time} | "
                f"인원: {people} | "
                f"전화번호: {phone} | "
                f"메뉴: {menu} | "
                f"결제금액: {payment}"
            )

        except StaleElementReferenceException:

            logging.warning(
                f"{i + 1}번 예약 요소가 변경되었습니다."
            )

        except Exception as e:

            logging.error(
                f"{i + 1}번 예약 수집 실패: {e}"
            )

    logging.info(
        f"예약 데이터 수집 완료: {len(reservation_data)}건"
    )

    return reservation_data


###############################################################################
# 12. Google Sheets 기록
###############################################################################

def save_reservations(sheet, reservation_data):

    if not reservation_data:

        logging.info(
            "기록할 예약 데이터가 없습니다."
        )

        return

    sheet.append_rows(
        reservation_data,
        value_input_option="USER_ENTERED"
    )

    logging.info("=" * 50)
    logging.info("Google Sheets 기록 완료")
    logging.info(
        f"총 기록 건수: {len(reservation_data)}건"
    )
    logging.info("=" * 50)


###############################################################################
# 13. 메인 실행
###############################################################################

def main():

    setup_logging()

    logging.info("=" * 50)
    logging.info("송도 네이버 예약 자동화 시작")
    logging.info("=" * 50)

    # 환경변수
    (
        naver_id,
        naver_pw,
        service_account_json_b64
    ) = get_environment_variables()

    # Google Sheets 인증
    sheets_manager = GoogleSheetsManager(
        service_account_json_b64
    )

    sheets_manager.authenticate()

    sheets_manager.open_spreadsheet(
        "송도 일일/월말 정산서"
    )

    sheet = sheets_manager.get_worksheet(
        "예약&마케팅"
    )

    logging.info("Google Sheets 인증 완료")

    # Selenium 실행
    with SeleniumDriverManager(
        headless=True
    ) as driver:

        try:

            # 네이버 로그인
            naver_login(
                driver,
                naver_id,
                naver_pw
            )

            # 예약·주문 탭
            enter_reservation_tab(
                driver
            )

            # 송도점 예약관리
            enter_songdo_reservation(
                driver
            )

            # 예약 수집
            reservation_data = collect_reservations(
                driver
            )

            # Google Sheets 기록
            save_reservations(
                sheet,
                reservation_data
            )

        except Exception:

            logging.error(
                "자동화 실행 중 오류 발생"
            )

            logging.error(
                traceback.format_exc()
            )

            save_debug_files(driver)

            raise

    logging.info("송도 네이버 예약 자동화 종료")


if __name__ == "__main__":

    main()


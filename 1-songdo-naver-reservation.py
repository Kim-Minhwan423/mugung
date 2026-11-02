
import os
import time
import json
import base64
import gspread

from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
    StaleElementReferenceException
)

from webdriver_manager.chrome import ChromeDriverManager


# =========================
# 1. 환경변수 및 Google 인증
# =========================

NAVER_ID = os.getenv("NAVER_ID")
NAVER_PW = os.getenv("NAVER_PW")
SERVICE_ACCOUNT_JSON_BASE64 = os.getenv(
    "SERVICE_ACCOUNT_JSON_BASE64"
)

if not NAVER_ID or not NAVER_PW:
    raise ValueError("NAVER_ID 또는 NAVER_PW가 없습니다.")

if not SERVICE_ACCOUNT_JSON_BASE64:
    raise ValueError("SERVICE_ACCOUNT_JSON_BASE64가 없습니다.")

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Base64 JSON 디코딩
service_account_json = json.loads(
    base64.b64decode(
        SERVICE_ACCOUNT_JSON_BASE64
    ).decode("utf-8")
)

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    service_account_json,
    scope
)

client = gspread.authorize(creds)

spreadsheet = client.open("송도 일일/월말 정산서")
sheet = spreadsheet.worksheet("예약&마케팅")

print("Google Sheets 인증 완료")


# =========================
# 2. Selenium 초기화
# =========================

user_agent = (
    "Mozilla/5.0 (Linux; Android 10; SM-G973N) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)

options = webdriver.ChromeOptions()

options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--disable-software-rasterizer")
options.add_argument("--remote-debugging-port=9222")
options.add_argument("--lang=ko-KR")
options.add_argument("--window-size=412,915")
options.add_argument(f"user-agent={user_agent}")

options.page_load_strategy = "eager"

driver = None

try:

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    driver.set_page_load_timeout(40)

    wait = WebDriverWait(driver, 20)

    # =========================
    # 3. 네이버 스마트플레이스 접속
    # =========================

    print("스마트플레이스 접속 시작")

    driver.get("https://new.smartplace.naver.com/")

    # 로그인 페이지 진입
    login_link = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            '//*[@id="modal-root"]/div/header/div/div/div[1]/a'
        ))
    )

    login_link.click()

    print("로그인 페이지 진입")

    # 아이디 입력
    id_input = wait.until(
        EC.presence_of_element_located((By.ID, "id"))
    )

    id_input.clear()
    id_input.send_keys(NAVER_ID)

    # 비밀번호 입력
    pw_input = wait.until(
        EC.presence_of_element_located((By.ID, "pw"))
    )

    pw_input.clear()
    pw_input.send_keys(NAVER_PW)

    # 로그인 버튼
    login_button = wait.until(
        EC.element_to_be_clickable((By.ID, "loginBtn_row"))
    )

    login_button.click()

    print("네이버 로그인 버튼 클릭 완료")

    # =========================
    # 4. 예약·주문 탭 진입
    # =========================

    reservation_tab_xpath = (
        '//*[@id="modal-root"]/div/div/div/div/div/div[2]/ul/li[3]/a'
    )

    reservation_tab = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            reservation_tab_xpath
        ))
    )

    reservation_tab.click()

    print("예약·주문 탭 진입 완료")

    # =========================
    # 5. 송도점 예약관리 진입
    # =========================

    songdo_button_xpath = (
        '//*[@id="modal-root"]/div/div/div/div/div[2]/div/div/'
        'ul/li[1]/div[2]/div/div[2]/div/button[1]'
    )

    songdo_button = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            songdo_button_xpath
        ))
    )

    songdo_button.click()

    print("송도점 예약관리 진입 완료")

    # =========================
    # 6. 예약 목록 로딩
    # =========================

    reservation_container_xpath = (
        '//*[@id="app"]/div/div[2]/div[2]/div/div[3]/div[3]/div/div[2]'
    )

    wait.until(
        EC.presence_of_element_located((
            By.XPATH,
            reservation_container_xpath
        ))
    )

    time.sleep(3)

    reservation_xpath = reservation_container_xpath + "/a"

    reservation_elements = driver.find_elements(
        By.XPATH,
        reservation_xpath
    )

    total_count = len(reservation_elements)

    print(f"현재 예약 목록: {total_count}건")

    # =========================
    # 7. 예약 정보 추출 함수
    # =========================

    def get_text(parent, xpath):

        try:

            element = parent.find_element(
                By.XPATH,
                xpath
            )

            return (element.text or "").strip()

        except NoSuchElementException:

            return ""

    # =========================
    # 8. 예약 정보 수집
    # =========================

    reservation_data = []

    for i in range(total_count):

        try:

            # 예약 요소 재조회
            reservations = driver.find_elements(
                By.XPATH,
                reservation_xpath
            )

            if i >= len(reservations):
                print(f"{i + 1}번 예약 요소가 사라졌습니다.")
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

            print(
                f"[{i + 1}/{total_count}] "
                f"상태: {status} | "
                f"날짜: {date_time} | "
                f"인원: {people} | "
                f"전화번호: {phone} | "
                f"메뉴: {menu} | "
                f"결제금액: {payment}"
            )

        except StaleElementReferenceException:

            print(f"{i + 1}번 예약: 화면 갱신으로 요소가 변경되었습니다.")

        except Exception as e:

            print(f"{i + 1}번 예약 수집 오류: {e}")

    # =========================
    # 9. Google Sheets 기록
    # =========================

    if reservation_data:

        sheet.append_rows(
            reservation_data,
            value_input_option="USER_ENTERED"
        )

        print("=" * 40)
        print("Google Sheets 기록 완료")
        print(f"총 수집 건수: {len(reservation_data)}건")
        print("=" * 40)

    else:

        print("수집된 예약 데이터가 없습니다.")

except Exception as e:

    print(f"자동화 실행 오류: {e}")

    raise

finally:

    if driver:

        driver.quit()

        print("브라우저 종료 완료")


import time
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
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# 모바일 User-Agent (모바일 DOM 유도)
user_agent = (
    "Mozilla/5.0 (Linux; Android 10; SM-G973N) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)

# Google Sheets API 인증
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
json_path = "/tmp/keyfile.json"  # 서비스 계정 키 경로
creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
client = gspread.authorize(creds)

spreadsheet = client.open("송도 일일/월말 정산서")
sheet = spreadsheet.worksheet("예약&마케팅")

# =========================
# Selenium 초기화 (모바일/헤드리스)
# =========================
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--disable-software-rasterizer")
options.add_argument("--remote-debugging-port=9222")
options.add_argument("--lang=ko-KR")
options.add_argument("--window-size=412,915")  # 모바일 화면 비율(갤럭시S급)
options.add_argument(f"user-agent={user_agent}")
options.page_load_strategy = "eager"

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)
driver.set_page_load_timeout(40)

# =========================
# 네이버 스마트플레이스 접속
# =========================
import os

NAVER_ID = os.environ["day9brewingco"]
NAVER_PW = os.environ["NAVER_PW"]

wait = WebDriverWait(driver, 20)

try:
    print("네이버 스마트플레이스 접속 시작")

    driver.get("https://new.smartplace.naver.com/")

    # 1. 로그인 페이지 진입
    login_link = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            '//*[@id="modal-root"]/div/header/div/div/div[1]/a'
        ))
    )
    login_link.click()

    print("로그인 페이지 진입")

    # 2. 아이디 입력
    id_input = wait.until(
        EC.presence_of_element_located((By.ID, "id"))
    )
    id_input.clear()
    id_input.send_keys(NAVER_ID)

    # 3. 비밀번호 입력
    pw_input = driver.find_element(By.ID, "pw")
    pw_input.clear()
    pw_input.send_keys(NAVER_PW)

    # 4. 로그인 버튼 클릭
    login_button = wait.until(
        EC.element_to_be_clickable((By.ID, "loginBtn_row"))
    )
    login_button.click()

    print("로그인 버튼 클릭 완료")

    # 로그인 이후 화면 대기
    time.sleep(3)

    # 5. 예약·주문 탭 진입
    reservation_tab = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            '//*[@id="modal-root"]/div/div/div/div/div/div[2]/ul/li[3]/a'
        ))
    )
    reservation_tab.click()

    print("예약·주문 탭 진입")

    time.sleep(3)

    # 6. 송도점 예약관리 버튼 클릭
    songdo_button = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            '//*[@id="modal-root"]/div/div/div/div/div[2]/div/div/ul/li[1]/div[2]/div/div[2]/div/button[1]'
        ))
    )
    songdo_button.click()

    print("송도점 예약관리 진입")

    # 7. 예약 목록 로딩 대기
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

    # =========================
    # 예약 데이터 수집
    # =========================

    # 예약 카드의 공통 부모 XPath
    reservation_xpath = reservation_container_xpath + "/a"

    reservation_elements = driver.find_elements(
        By.XPATH,
        reservation_xpath
    )

    total_count = len(reservation_elements)

    print(f"현재 화면 예약 건수: {total_count}")

    reservation_data = []

    # 개별 요소의 텍스트 추출 함수
    def get_text(parent, xpath):
        try:
            return parent.find_element(
                By.XPATH, xpath
            ).get_attribute("innerText").strip()
        except NoSuchElementException:
            return ""

    # 예약 1번부터 마지막 예약까지 반복
    for i in range(total_count):

        try:
            # 화면 갱신에 대비해 매번 요소 재조회
            reservations = driver.find_elements(
                By.XPATH,
                reservation_xpath
            )

            reservation = reservations[i]

            # 1. 예약 상태
            status = get_text(
                reservation,
                "./div[2]"
            )

            # 2. 날짜 및 시간
            date_time = get_text(
                reservation,
                "./div[6]/div/a/div[1]"
            )

            # 3. 예약 인원
            people = get_text(
                reservation,
                "./div[6]/div/a/div[3]"
            )

            # 4. 휴대폰 번호
            phone = get_text(
                reservation,
                "./div[4]"
            )

            # 5. 예약 메뉴
            menu = get_text(
                reservation,
                "./div[6]/div/a/div[4]"
            )

            # 6. 결제 금액
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

        except Exception as e:
            print(f"[{i + 1}번 예약 수집 오류] {e}")

    # =========================
    # Google Sheets 기록
    # =========================

    if reservation_data:

        sheet.append_rows(
            reservation_data,
            value_input_option="USER_ENTERED"
        )

        print(
            f"구글 시트 기록 완료: "
            f"{len(reservation_data)}건"
        )

    else:
        print("수집된 예약 데이터가 없습니다.")

except Exception as e:

    print(f"자동화 실행 중 오류 발생: {e}")

    raise

finally:
    driver.quit()


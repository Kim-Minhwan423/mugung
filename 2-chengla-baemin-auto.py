import os
import time
import gspread
import traceback
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# ================================
# 1. Google Sheets API 인증 설정
# ================================
# User-Agent 설정
user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    " AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/120.0.0.0 Safari/537.36"
)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# GitHub Actions용: /tmp/keyfile.json 경로 (헤드리스 서버에서)
json_path = "/tmp/keyfile.json"  
creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
client = gspread.authorize(creds)

# 스프레드시트 열기 (예시)
spreadsheet = client.open("청라 일일/월말 정산서")  # 스프레드시트 이름

sheet_inventory = spreadsheet.worksheet("재고")    # '재고' 시트 선택
sheet_report = spreadsheet.worksheet("무궁 청라")  # '무궁 청라' 시트 선택

# ================================
# 2. Chrome WebDriver 실행
# ================================
# --- 헤드리스 모드 + 한국어/ko-KR 설정 ---
options = webdriver.ChromeOptions()

# 1) Headless (GUI 없이 동작)
options.add_argument("--headless=new")  # 최신 headless 모드 사용

# 2) 서버 환경 안정성 옵션
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")

# 3) 언어 설정
options.add_argument("--lang=ko-KR")
options.add_experimental_option("prefs", {
    "intl.accept_languages": "ko,ko-KR"
})

# 4) 기타 설정
options.add_argument("--window-size=1920,1080")
options.add_argument(f"user-agent={user_agent}")

# ChromeDriver 설치 및 WebDriver 초기화
driver = webdriver.Chrome(
    service=ChromeService(ChromeDriverManager().install()),
    options=options
)

# ================================
# 3. 자동화 작업 수행
# ================================
try:
    wait = WebDriverWait(driver, 20)  # Explicit wait

    # 3.1. 사이트 접속
    driver.get("https://self.baemin.com/")
    print("사이트에 접속 중...")

    # 3.2. 사용자명 입력
    username_selector = "#root > div.style__LoginWrap-sc-145yrm0-0.hKiYRl > div > div > form > div:nth-child(1) > span > input[type=text]"
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, username_selector)))
    username_input = driver.find_element(By.CSS_SELECTOR, username_selector)
    username_input.clear()
    username_input.send_keys("mugung876")
    print("사용자명을 입력했습니다.")

    # 3.3. 비밀번호 입력
    password_selector = "#root > div.style__LoginWrap-sc-145yrm0-0.hKiYRl > div > div > form > div.Input__InputWrap-sc-tapcpf-1.kjWnKT.mt-half-3 > span > input[type=password]"
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, password_selector)))
    password_input = driver.find_element(By.CSS_SELECTOR, password_selector)
    password_input.clear()
    password_input.send_keys("Zz1070619!")
    print("비밀번호를 입력했습니다.")

    # 3.4. 로그인 버튼 클릭
    login_button_selector = "#root > div.style__LoginWrap-sc-145yrm0-0.hKiYRl > div > div > form > button"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, login_button_selector)))
    login_button = driver.find_element(By.CSS_SELECTOR, login_button_selector)
    login_button.click()
    print("로그인 버튼을 클릭했습니다.")

    # 3.5. 로그인 후 페이지 로딩 대기
    # 예: 특정 요소가 나타날 때까지 대기 (여기서는 메뉴 버튼)
    menu_button_selector = "#root > div > div.Container_c_lr2y_1utdzds5.MobileHeader-module__mihN > div > div > div:nth-child(1) > button > span > span > svg"
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, menu_button_selector)))
    print("로그인 후 페이지가 로드되었습니다.")

    # 3.6. 팝업 닫기
    try:
        popup_close_selector = "body > div.bsds-portal > div > section > footer > div > button > span > span"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, popup_close_selector)))
        popup_close_button = driver.find_element(By.CSS_SELECTOR, popup_close_selector)
        popup_close_button.click()
        print("팝업을 닫았습니다.")
    except TimeoutException:
        print("팝업이 나타나지 않았거나 이미 닫혔습니다.")

    # 3.7. 메뉴 버튼 클릭하여 메뉴창 열기
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector)))
    menu_button = driver.find_element(By.CSS_SELECTOR, menu_button_selector)
    menu_button.click()
    print("메뉴 버튼을 클릭하여 메뉴창을 열었습니다.")

    # 3.8. '주문내역' 클릭
    order_history_selector = "#root > div > div.frame-container.lnb-open > div.frame-aside > nav > div.MenuList-module__lZzf.LNB-module__foKc > ul:nth-child(10) > a:nth-child(1) > button > div.ListItem_c_lr2y_hbrir4i.c_lr2y_13c33de0 > div > div > p"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, order_history_selector)))
    order_history_button = driver.find_element(By.CSS_SELECTOR, order_history_selector)
    order_history_button.click()
    print("'주문내역'을 클릭했습니다.")

    # 3.9. 주문내역 페이지 로딩 대기
    # 예: 날짜 필터 버튼이 나타날 때까지 대기
    date_filter_button_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.FilterContainer-module___Rxt > button.FilterContainer-module__vSPY.FilterContainer-module__vOLM"
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, date_filter_button_selector)))
    print("주문내역 페이지가 로드되었습니다.")

    # 3.10. 날짜 필터 버튼 클릭
    date_filter_button = driver.find_element(By.CSS_SELECTOR, date_filter_button_selector)
    date_filter_button.click()
    print("날짜 필터 버튼을 클릭했습니다.")

    # 3.11. '일자별' 선택
    daily_filter_selector = "#\\:rs\\: > div.Container_c_lr2y_1utdzds5.PageSheet_b_lydv_1pb26is9 > div.DefaultDateFilter-module__wiPF > fieldset > div > div:nth-child(1)"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, daily_filter_selector)))
    daily_filter = driver.find_element(By.CSS_SELECTOR, daily_filter_selector)
    daily_filter.click()
    print("'일자별' 필터를 선택했습니다.")

    # 3.12. '오늘' 날짜 선택
    today_selector = "#\\:rs\\: > div.Container_c_lr2y_1utdzds5.PageSheet_b_lydv_1pb26is9 > div.DefaultDateFilter-module__wiPF > div > div:nth-child(1)"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, today_selector)))
    today_option = driver.find_element(By.CSS_SELECTOR, today_selector)
    today_option.click()
    print("'오늘' 날짜를 선택했습니다.")

    # 3.13. '적용' 버튼 클릭
    apply_button_selector = "#\\:rs\\: > div.Container_c_lr2y_1utdzds5.OverlayFooter_b_lydv_1slqmfa0.OverlayFooter_b_lydv_1slqmfa1 > button > span > span > span"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, apply_button_selector)))
    apply_button = driver.find_element(By.CSS_SELECTOR, apply_button_selector)
    apply_button.click()
    print("'적용' 버튼을 클릭했습니다.")

    # 3.14. 필터 적용 후 데이터 로딩 대기
    # 예: 주문 목록이 업데이트될 때까지 잠시 대기
    time.sleep(3)  # 적절한 대기 시간 조정 가능
    print("필터가 적용되고 데이터가 로드되었습니다.")

    # 추가적인 작업을 여기에 추가할 수 있습니다.
    # 예: 주문 데이터를 추출하여 Google Sheets에 기록

except Exception as e:
    print("오류가 발생했습니다:")
    traceback.print_exc()
finally:
    # 드라이버 종료
    driver.quit()
    print("WebDriver를 종료했습니다.")

import os
import base64
import logging
import sys
import time
import random
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("automation.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# 2. 구글 시트 인증을 위한 서비스 계정 설정 함수
def setup_google_credentials():
    json_base64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")
    if not json_base64:
        logging.error("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    try:
        logging.info("SERVICE_ACCOUNT_JSON_BASE64 디코딩을 시작합니다.")
        json_bytes = base64.b64decode(json_base64)
        logging.info("Base64 디코딩이 성공적으로 완료되었습니다.")

        json_path = "/tmp/keyfile.json"

        with open(json_path, "wb") as f:
            f.write(json_bytes)
        logging.info(f"서비스 계정 JSON 파일을 {json_path}으로 저장했습니다.")
        return json_path
    except base64.binascii.Error as e:
        logging.error("Base64 디코딩 오류 발생.")
        logging.error(f"오류 내용: {e}")
        raise
    except Exception as e:
        logging.error("서비스 계정 JSON 디코딩 중 오류 발생.")
        logging.error(f"오류 내용: {e}")
        raise

# 3. 구글 시트 인증 함수
def authorize_google_sheets(json_path):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        credentials = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
        client = gspread.authorize(credentials)
        logging.info("Google Sheets API 인증에 성공했습니다.")
        return client
    except Exception as e:
        logging.error("Google Sheets API 인증 실패.")
        logging.error(f"오류 내용: {e}")
        raise

# 4. Selenium WebDriver 초기화 함수
def initialize_webdriver(user_agent):
    try:
        options = webdriver.ChromeOptions()

        # 헤드리스 모드
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1020,980")
        options.add_argument(f"user-agent={user_agent}")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        # 브라우저 속성 수정하여 자동화 감지 방지
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })

        logging.info("WebDriver가 성공적으로 초기화되었습니다.")
        return driver
    except WebDriverException as e:
        logging.error("WebDriver 초기화에 실패했습니다.")
        logging.error(f"{str(e)}")
        raise

# 5. 랜덤 지연 시간 추가 함수
def random_delay(min_seconds=2, max_seconds=5):
    delay = random.uniform(min_seconds, max_seconds)
    logging.info(f"랜덤 지연 시간: {delay:.2f}초 대기합니다.")
    time.sleep(delay)

# 6. 디버그 파일 저장 함수
def save_debug_files(driver, filename_prefix):
    screenshot_path = f"{filename_prefix}.png"
    html_path = f"{filename_prefix}.html"
    try:
        driver.save_screenshot(screenshot_path)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logging.info(f"{screenshot_path}과 {html_path} 파일을 생성했습니다.")
    except Exception as e:
        logging.error(f"디버그 파일 저장 중 오류 발생: {e}")

# 7. 로그인 함수
def login(driver, wait, username, password):
    try:
        driver.get("https://self.baemin.com/")
        logging.info("배민 사이트에 접속 중...")

        # 현재 URL과 타이틀 로그
        logging.info(f"현재 URL: {driver.current_url}")
        logging.info(f"페이지 타이틀: {driver.title}")

        # 로그인 시도 전 스크린샷 저장
        save_debug_files(driver, "before_login")

        # 로그인 컨테이너 XPath
        main_container_xpath = "//div[contains(@class, 'LoginWrap')]"
        wait.until(EC.presence_of_element_located((By.XPATH, main_container_xpath)))
        logging.info("배민 로그인 페이지 로드 완료.")

        # 사용자명 입력
        username_xpath = "//input[@type='text' and @name='username']"  # 실제 name 속성 확인 필요
        wait.until(EC.presence_of_element_located((By.XPATH, username_xpath)))
        username_input = driver.find_element(By.XPATH, username_xpath)
        username_input.clear()
        username_input.send_keys(username)
        logging.info("사용자명을 입력했습니다.")

        # 랜덤 지연 시간 추가
        random_delay()

        # 비밀번호 입력
        password_xpath = "//input[@type='password' and @name='password']"  # 실제 name 속성 확인 필요
        wait.until(EC.presence_of_element_located((By.XPATH, password_xpath)))
        password_input = driver.find_element(By.XPATH, password_xpath)
        password_input.clear()
        password_input.send_keys(password)
        logging.info("비밀번호를 입력했습니다.")

        # 랜덤 지연 시간 추가
        random_delay()

        # 로그인 버튼 클릭
        login_button_xpath = "//button[contains(text(), '로그인')]"  # 버튼 텍스트 확인 필요
        wait.until(EC.element_to_be_clickable((By.XPATH, login_button_xpath)))
        login_button = driver.find_element(By.XPATH, login_button_xpath)
        login_button.click()
        logging.info("로그인 버튼을 클릭했습니다.")

        # 랜덤 지연 시간 추가
        random_delay()

        # 로그인 완료 확인 (메뉴 버튼 등장)
        menu_button_xpath = "//div[contains(@class, 'MobileHeader')]//div[contains(@class, 'MenuButton')]"
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, menu_button_xpath)))
            logging.info("로그인에 성공했습니다.")

            # 로그인 성공 후 스크린샷 및 HTML 저장
            save_debug_files(driver, "after_login_success")

        except TimeoutException:
            # 로그인 실패 시 스크린샷 및 페이지 소스 저장
            save_debug_files(driver, "after_login_timeout")
            logging.error("로그인 페이지 로드 또는 로그인에 실패했습니다. 스크린샷과 페이지 소스를 확인하세요.")
            raise

    except TimeoutException:
        logging.error("로그인 페이지 로드 또는 로그인에 실패했습니다.")
        save_debug_files(driver, "after_login_exception")
        raise
    except Exception as e:
        logging.error("로그인 처리 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        save_debug_files(driver, "after_login_error")
        raise

# 8. 팝업 닫기 함수 (필요 시 구현)
def close_popup(driver, wait):
    try:
        # 팝업 닫기 로직 구현
        popup_close_xpath = "//button[contains(@class, 'popup-close')]"  # 실제 닫기 버튼 XPath 확인 필요
        wait.until(EC.element_to_be_clickable((By.XPATH, popup_close_xpath)))
        popup_close_button = driver.find_element(By.XPATH, popup_close_xpath)
        popup_close_button.click()
        logging.info("팝업을 성공적으로 닫았습니다.")
    except TimeoutException:
        logging.info("닫을 팝업이 없거나 이미 닫혔습니다.")
    except Exception as e:
        logging.error(f"팝업 닫기 중 오류 발생: {e}")
        raise

# 9. 주문내역 페이지로 이동 함수 (필요 시 구현)
def navigate_to_order_history(driver, wait):
    try:
        logging.info("주문내역 페이지로 이동을 시도합니다.")
        # 메뉴 버튼 클릭
        menu_button_xpath = "//div[contains(@class, 'MobileHeader')]//div[contains(@class, 'MenuButton')]"
        wait.until(EC.element_to_be_clickable((By.XPATH, menu_button_xpath)))
        menu_button = driver.find_element(By.XPATH, menu_button_xpath)
        menu_button.click()
        logging.info("메뉴 버튼을 클릭하여 메뉴창을 열었습니다.")

        # 주문내역 버튼 클릭
        order_history_button_xpath = "//button[contains(text(), '주문내역')]"  # 실제 버튼 텍스트 확인 필요
        wait.until(EC.element_to_be_clickable((By.XPATH, order_history_button_xpath)))
        order_history_button = driver.find_element(By.XPATH, order_history_button_xpath)
        order_history_button.click()
        logging.info("'주문내역' 버튼을 클릭했습니다.")

        # 주문내역 페이지 로드 확인
        date_filter_button_xpath = "//button[contains(text(), '날짜 필터')]"  # 실제 버튼 텍스트 확인 필요
        wait.until(EC.presence_of_element_located((By.XPATH, date_filter_button_xpath)))
        logging.info("주문내역 페이지가 로드되었습니다.")

        # 성공 시 스크린샷 저장
        save_debug_files(driver, "navigate_order_history_success")

    except TimeoutException:
        logging.error("주문내역 페이지로 이동하는 데 실패했습니다.")
        save_debug_files(driver, "navigate_order_history_timeout")
        raise
    except Exception as e:
        logging.error(f"주문내역 페이지로 이동 중 오류 발생: {e}")
        save_debug_files(driver, "navigate_order_history_error")
        raise

# 10. 날짜 필터 설정 함수 (필요 시 구현)
def set_date_filter(driver, wait):
    try:
        logging.info("날짜 필터를 설정합니다.")
        # 날짜 필터 설정 로직 구현
        # 예시: 특정 날짜 선택, 필터 적용 버튼 클릭 등
        # 날짜 필터 버튼 XPath 예시
        date_filter_button_xpath = "//button[contains(text(), '날짜 필터')]"  # 실제 XPath 확인 필요
        wait.until(EC.element_to_be_clickable((By.XPATH, date_filter_button_xpath)))
        date_filter_button = driver.find_element(By.XPATH, date_filter_button_xpath)
        date_filter_button.click()
        logging.info("날짜 필터 버튼을 클릭했습니다.")

        # 특정 날짜 범위 선택 (예시)
        start_date_xpath = "//input[@name='startDate']"  # 실제 XPath 확인 필요
        end_date_xpath = "//input[@name='endDate']"      # 실제 XPath 확인 필요

        wait.until(EC.presence_of_element_located((By.XPATH, start_date_xpath)))
        start_date_input = driver.find_element(By.XPATH, start_date_xpath)
        start_date_input.clear()
        start_date_input.send_keys("2025-01-01")  # 실제 원하는 시작 날짜로 변경

        wait.until(EC.presence_of_element_located((By.XPATH, end_date_xpath)))
        end_date_input = driver.find_element(By.XPATH, end_date_xpath)
        end_date_input.clear()
        end_date_input.send_keys("2025-01-25")    # 실제 원하는 종료 날짜로 변경

        # 필터 적용 버튼 클릭
        apply_filter_button_xpath = "//button[contains(text(), '적용')]"  # 실제 XPath 확인 필요
        wait.until(EC.element_to_be_clickable((By.XPATH, apply_filter_button_xpath)))
        apply_filter_button = driver.find_element(By.XPATH, apply_filter_button_xpath)
        apply_filter_button.click()
        logging.info("날짜 필터를 적용했습니다.")

        # 필터 적용 후 스크린샷 저장
        save_debug_files(driver, "set_date_filter_success")

    except TimeoutException:
        logging.error("날짜 필터 설정 중 타임아웃이 발생했습니다.")
        save_debug_files(driver, "set_date_filter_timeout")
        raise
    except Exception as e:
        logging.error(f"날짜 필터 설정 중 오류 발생: {e}")
        save_debug_files(driver, "set_date_filter_error")
        raise

# 11. 주문 요약 추출 함수 (필요 시 구현)
def extract_order_summary(driver, wait):
    try:
        logging.info("주문 요약을 추출합니다.")
        # 주문 요약 추출 로직 구현
        # 예시: 특정 요소의 텍스트 추출
        summary_xpath = "//div[@id='order-summary']"  # 실제 XPath 확인 필요
        wait.until(EC.presence_of_element_located((By.XPATH, summary_xpath)))
        summary_element = driver.find_element(By.XPATH, summary_xpath)
        summary_text = summary_element.text.strip()
        logging.info(f"주문 요약: {summary_text}")
        return summary_text

    except TimeoutException:
        logging.error("주문 요약을 추출하는 데 실패했습니다.")
        save_debug_files(driver, "extract_order_summary_timeout")
        raise
    except Exception as e:
        logging.error(f"주문 요약 추출 중 오류 발생: {e}")
        save_debug_files(driver, "extract_order_summary_error")
        raise

# 12. 주문 요약을 구글 시트에 업데이트하는 함수 (필요 시 구현)
def update_order_summary_sheet(sheet, summary_text):
    try:
        logging.info("주문 요약을 구글 시트에 업데이트합니다.")
        # 시트 업데이트 로직 구현
        # 예시: 특정 셀에 텍스트 쓰기
        sheet.update('A1', summary_text)
        logging.info("주문 요약이 구글 시트에 성공적으로 업데이트되었습니다.")
    except Exception as e:
        logging.error(f"구글 시트 업데이트 중 오류 발생: {e}")
        raise

# 13. '재고' 시트 특정 범위 삭제 함수 (필요 시 구현)
def clear_inventory_sheet(sheet):
    try:
        logging.info("재고 시트의 특정 범위를 삭제합니다.")
        # 특정 범위 삭제 로직 구현
        # 예시: 특정 셀 범위 초기화
        sheet.batch_clear(['A1:B10'])  # 실제 범위로 수정
        logging.info("재고 시트의 특정 범위가 성공적으로 삭제되었습니다.")
    except Exception as e:
        logging.error(f"'재고' 시트 삭제 중 오류 발생: {e}")
        raise

# 14. 판매 수량을 '재고' 시트에 기록하는 함수 (필요 시 구현)
def extract_and_update_sales_data(driver, wait, sheet, item_to_cell):
    try:
        logging.info("판매 수량을 추출하여 '재고' 시트에 기록합니다.")
        # 판매 데이터 추출 및 시트 업데이트 로직 구현
        # 예시: 테이블에서 데이터 추출
        sales_data = {}
        # 여기에 데이터 추출 로직 추가

        # 예시: sales_data 딕셔너리를 시트에 업데이트
        batch = []
        for cell_address, qty in sales_data.items():
            batch.append({'range': cell_address, 'values': [[qty]]})
            logging.info(f"배치 업데이트 준비: {cell_address} = {qty}")
        if batch:
            sheet.batch_update(batch)
            logging.info("'재고' 시트 배치 업데이트 완료.")
        else:
            logging.info("판매 데이터가 없습니다.")

    except Exception as e:
        logging.error("판매 수량 추출/기록 중 오류 발생:")
        logging.error(f"{str(e)}")
        raise

# 15. 메인 함수
def main():
    print("스크립트가 시작되었습니다.")

    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/132.0.6834.110 Safari/537.36"
    )

    # 구글 시트 인증을 위한 서비스 계정 JSON 설정
    try:
        json_path = setup_google_credentials()
    except Exception as e:
        logging.error("구글 시트 인증을 위한 서비스 계정 설정 실패.")
        sys.exit(1)
    
    try:
        # 구글 시트 인증
        client = authorize_google_sheets(json_path)
        spreadsheet = client.open("청라 일일/월말 정산서")
        muGung_sheet = spreadsheet.worksheet("무궁 청라")
        inventory_sheet = spreadsheet.worksheet("재고")
    except Exception as e:
        logging.error("구글 시트 인증 또는 시트 접근 중 오류 발생.")
        sys.exit(1)

    # WebDriver (Headless)
    driver = initialize_webdriver(user_agent)
    wait = WebDriverWait(driver, 60)  # 타임아웃 시간 연장

    try:
        # 배민 ID/PW 체크
        BAEMIN_USERNAME = os.getenv("CHENGLA_BAEMIN_ID")
        BAEMIN_PASSWORD = os.getenv("CHENGLA_BAEMIN_PW")
        if not BAEMIN_USERNAME or not BAEMIN_PASSWORD:
            raise ValueError("CHENGLA_BAEMIN_ID 혹은 CHENGLA_BAEMIN_PW 환경변수가 설정되지 않았습니다.")

        # 로그인 & 팝업 닫기
        login(driver, wait, BAEMIN_USERNAME, BAEMIN_PASSWORD)
        close_popup(driver, wait)

        # 주문내역 → 날짜 필터
        navigate_to_order_history(driver, wait)
        set_date_filter(driver, wait)

        # 주문 요약 → 구글 시트
        summary_text = extract_order_summary(driver, wait)
        update_order_summary_sheet(muGung_sheet, summary_text)

        # '재고' 시트 특정 범위 삭제
        clear_inventory_sheet(inventory_sheet)

        # 판매 수량 → '재고' 시트 기록
        item_to_cell = {
            '육회비빔밥(1인분)': 'P43',
            '꼬리곰탕(1인분)': 'E38',
            '빨간곰탕(1인분)': 'E39',
            '꼬리덮밥(1인분)': 'E40',
            '육전(200g)': 'P44',
            '육회(300g)': 'P42',
            '육사시미(250g)': 'P41',
            '꼬리수육(2인분)': 'E41',
            '소꼬리찜(2인분)': 'E42',
            '불꼬리찜(2인분)': 'E43',
            '로제꼬리(2인분)': 'E44',
            '꼬리구이(2인분)': 'E45',
            '코카콜라': 'AD42',
            '스프라이트': 'AD43',
            '토닉워터': 'AD44',
            '제로콜라': 'AD41',
            '만월': 'AP39',
            '문배술25': 'AP40',
            '로아 화이트': 'AP43',
            '황금보리': 'AP38',
            '왕율주': 'AP41',
            '왕주': 'AP42',
            '청하': 'BA38',
            '참이슬 후레쉬': 'BA39',
            '처음처럼': 'BA40',
            '새로': 'BA42',
            '진로이즈백': 'BA41',
            '카스': 'BA43',
            '테라': 'BA44',
            '켈리': 'BA45',
            '소성주막걸리': 'AP45'
        }

        extract_and_update_sales_data(driver, wait, inventory_sheet, item_to_cell)

        # 스크립트가 성공적으로 끝난 후 최종 스크린샷 및 HTML 저장
        save_debug_files(driver, "after_script_success")

    except Exception as e:
        logging.error("프로세스 중 오류가 발생했습니다:")
        logging.error(f"{str(e)}")
        traceback.print_exc()
    finally:
        driver.quit()
        logging.info("WebDriver를 종료했습니다.")

if __name__ == "__main__":
    main()

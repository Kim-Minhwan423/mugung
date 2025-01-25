import os
import re
import datetime
import logging
import traceback
import sys
import time
import uuid  # user-data-dir (충돌 방지)용
import json
import base64  # Base64 디코딩을 위해 추가

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# oauth2client로 Google Sheets 인증
from oauth2client.service_account import ServiceAccountCredentials

import gspread
from gspread_formatting import CellFormat, NumberFormat, format_cell_range

# 환경변수에서 ID/PW/JSON_PATH
BAEMIN_USERNAME = os.getenv("CHENGLA_BAEMIN_ID")
BAEMIN_PASSWORD = os.getenv("CHENGLA_BAEMIN_PW")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/keyfile.json")
SERVICE_ACCOUNT_JSON_BASE64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")  # Base64 인코딩된 JSON

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)

file_handler = logging.FileHandler("script.log", encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)


# 1) Google Sheets 인증
def authorize_google_sheets(json_path):
    try:
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scopes)
        client = gspread.authorize(creds)
        logger.info("Google Sheets API 인증에 성공했습니다.")
        return client
    except Exception as e:
        logger.error("Google Sheets API 인증에 실패했습니다.")
        logger.error(f"{str(e)}")
        raise


# 2) Selenium WebDriver 초기화 (Headless)
def initialize_webdriver(user_agent):
    try:
        options = webdriver.ChromeOptions()

        # 헤드리스 모드 (디버깅 시 주석 처리 가능)
        options.add_argument("--headless")  # 필요 시 주석 처리하여 브라우저 창 표시

        # 안정성 옵션
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        # 창 사이즈 (필요하다면)
        options.add_argument("--window-size=1020,980")

        # User-Agent 설정 (필요 시)
        options.add_argument(f"user-agent={user_agent}")

        # 추가 최적화 옵션
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--remote-debugging-port=9222")

        # Headless 브라우저 감지 방지
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # WebDriver Manager를 통한 ChromeDriver 설정
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

# 3) 배민 로그인
import random
import time

def random_delay(min_seconds=2, max_seconds=5):
    delay = random.uniform(min_seconds, max_seconds)
    logging.info(f"랜덤 지연 시간: {delay:.2f}초 대기합니다.")
    time.sleep(delay)

def login(driver, wait, username, password):
    try:
        driver.get("https://self.baemin.com/")
        logging.info("배민 사이트에 접속 중...")

        # 현재 URL과 타이틀 로그
        logging.info(f"현재 URL: {driver.current_url}")
        logging.info(f"페이지 타이틀: {driver.title}")

        # 로그인 시도 전 스크린샷 저장
        driver.save_screenshot("before_login.png")
        logging.info("로그인 시도 전 스크린샷을 저장했습니다.")

        # 로그인 컨테이너 XPath 수정 (예시)
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
            driver.save_screenshot("after_login_success.png")
            with open("after_login_success.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logging.info("로그인 성공 후 스크린샷과 HTML 소스를 저장했습니다.")

        except TimeoutException:
            # 로그인 실패 시 스크린샷 및 페이지 소스 저장
            driver.save_screenshot("after_login_timeout.png")
            with open("after_login_timeout.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logging.error("로그인 페이지 로드 또는 로그인에 실패했습니다. 스크린샷과 페이지 소스를 확인하세요.")
            raise

    except TimeoutException:
        logging.error("로그인 페이지 로드 또는 로그인에 실패했습니다.")
        driver.save_screenshot("after_login_exception.png")
        with open("after_login_exception.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        raise
    except Exception as e:
        logging.error("로그인 처리 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        driver.save_screenshot("after_login_error.png")
        with open("after_login_error.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        raise

# 4) 팝업 닫기
def close_popup(driver, wait):
    popup_close_selector = "body > div.bsds-portal > div > section > footer > div > button"
    try:
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, popup_close_selector)))
        popup_close_button = driver.find_element(By.CSS_SELECTOR, popup_close_selector)
        popup_close_button.click()
        logging.info("팝업을 성공적으로 닫았습니다.")
    except TimeoutException:
        logging.warning("닫을 수 있는 팝업이 없거나 로드되지 않았습니다.")
    except Exception as e:
        logging.error("팝업을 닫는 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        raise


# 5) 주문내역 페이지 진입
def navigate_to_order_history(driver, wait):
    try:
        menu_button_selector = "#root > div > div.Container_c_9rpk_1utdzds5.MobileHeader-module__mihN > div > div > div:nth-child(1)"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector)))
        menu_button = driver.find_element(By.CSS_SELECTOR, menu_button_selector)
        menu_button.click()
        logging.info("메뉴 버튼을 클릭하여 메뉴창을 열었습니다.")

        order_history_selector = "#root > div > div.frame-container.lnb-open > div.frame-aside > nav > div.MenuList-module__lZzf.LNB-module__foKc > ul:nth-child(10) > a:nth-child(1) > button"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, order_history_selector)))
        order_history_button = driver.find_element(By.CSS_SELECTOR, order_history_selector)
        order_history_button.click()
        logging.info("'주문내역' 버튼을 클릭했습니다.")

        # 주문내역 페이지 로드
        date_filter_button_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.FilterContainer-module___Rxt > button"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, date_filter_button_selector)))
        logging.info("주문내역 페이지가 로드되었습니다.")

    except TimeoutException:
        logging.error("주문내역 페이지로 이동하는 데 실패했습니다.")
        driver.save_screenshot("navigate_order_history_timeout.png")
        raise
    except Exception as e:
        logging.error("주문내역 페이지로 이동 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        driver.save_screenshot("navigate_order_history_error.png")
        raise


# 6) 날짜 필터 설정
def set_date_filter(driver, wait):
    try:
        date_filter_button_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.FilterContainer-module___Rxt > button"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, date_filter_button_selector)))
        date_filter_button = driver.find_element(By.CSS_SELECTOR, date_filter_button_selector)
        date_filter_button.click()
        logging.info("날짜 필터 버튼을 클릭했습니다.")

        daily_filter_xpath = "//label[contains(., '일・주')]/preceding-sibling::input[@type='radio']"
        wait.until(EC.element_to_be_clickable((By.XPATH, daily_filter_xpath)))
        daily_filter = driver.find_element(By.XPATH, daily_filter_xpath)
        daily_filter.click()
        logging.info("'일・주' 필터를 선택했습니다.")

        apply_button_xpath = "//button[contains(., '적용')]"
        wait.until(EC.element_to_be_clickable((By.XPATH, apply_button_xpath)))
        apply_button = driver.find_element(By.XPATH, apply_button_xpath)
        apply_button.click()
        logging.info("'적용' 버튼을 클릭했습니다.")

        time.sleep(3)
        logging.info("3초 대기 완료.")

        summary_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.TotalSummary-module__sVL1 > div:nth-child(2) > span.TotalSummary-module__SysK > b"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, summary_selector)))
        logging.info("필터 적용 후 데이터가 로드되었습니다.")
    except TimeoutException:
        logging.error("날짜 필터 설정에 실패했습니다.")
        driver.save_screenshot("set_date_filter_timeout.png")
        raise
    except Exception as e:
        logging.error("날짜 필터 설정 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        driver.save_screenshot("set_date_filter_error.png")
        raise


# 7) 주문 요약 추출
def extract_order_summary(driver, wait):
    try:
        summary_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.TotalSummary-module__sVL1 > div:nth-child(2) > span.TotalSummary-module__SysK > b"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, summary_selector)))
        summary_element = driver.find_element(By.CSS_SELECTOR, summary_selector)
        summary_text = summary_element.text.strip()
        logging.info(f"주문 요약 데이터: {summary_text}")
        return summary_text
    except TimeoutException:
        logging.error("주문 요약 데이터를 추출하는 데 실패했습니다.")
        driver.save_screenshot("extract_order_summary_timeout.png")
        raise
    except NoSuchElementException:
        logging.error("주문 요약 데이터 요소를 찾을 수 없습니다.")
        driver.save_screenshot("extract_order_summary_no_element.png")
        raise
    except Exception as e:
        logging.error("주문 요약 데이터 추출 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        driver.save_screenshot("extract_order_summary_error.png")
        raise


# 8) Google Sheets에 주문 요약 데이터 기록
def update_order_summary_sheet(muGung_sheet, summary_text):
    try:
        today = datetime.datetime.today()
        day = today.day
        logging.info(f"오늘 일자: {day}")

        date_cells = muGung_sheet.range('U3:U33')
        day_list = [cell.value for cell in date_cells]

        day_str = str(day)
        if day_str in day_list:
            index = day_list.index(day_str)
            row_number = 3 + index
            target_column = 'V'
            target_cell = f"{target_column}{row_number}"

            summary_value = int(re.sub(r'[^\d]', '', summary_text))

            muGung_sheet.update(target_cell, [[summary_value]])
            logging.info(f"주문 요약 데이터를 {target_cell} 셀에 기록했습니다.")

            format_cell_range(muGung_sheet, 'V3:V33', CellFormat(
                numberFormat=NumberFormat(
                    type='NUMBER',
                    pattern='#,##0'
                )
            ))
            logging.info("V3:V33 셀 형식을 지정했습니다.")
        else:
            logging.warning(f"시트에 오늘 날짜({day})가 없습니다.")
    except ValueError:
        logging.error(f"데이터 형식 오류: '{summary_text}'")
        raise
    except Exception as e:
        logging.error("구글 시트 기록 중 오류 발생.")
        logging.error(f"{str(e)}")
        raise


# 9) '재고' 시트 범위 삭제
def clear_inventory_sheet(inventory_sheet):
    try:
        ranges_to_clear = ['E38:E45', 'P38:P45', 'AD38:AD45', 'AP38:AP45', 'BA38:BA45']
        inventory_sheet.batch_clear(ranges_to_clear)
        logging.info("'재고' 시트 지정 범위 삭제 완료.")
    except Exception as e:
        logging.error("재고 시트의 특정 범위 삭제 중 오류 발생.")
        logging.error(f"{str(e)}")
        raise


# 10) 판매 수량 추출 + '재고' 시트 기록
def extract_and_update_sales_data(driver, wait, inventory_sheet, item_to_cell):
    try:
        logging.info("판매 수량 추출을 시작합니다.")
        sales_data = {}

        while True:
            # 주문 목록 tr[1,3,5,...19]
            for order_num in range(1, 20, 2):
                if order_num == 1:
                    order_details_tr_num = 2
                    logging.info("첫 번째 주문 처리.")
                else:
                    order_button_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_num}]/td/div/div'
                    try:
                        order_button = driver.find_element(By.XPATH, order_button_xpath)
                        order_button.click()
                        logging.info(f"tr[{order_num}] 클릭됨.")

                        order_details_tr_num = order_num + 1
                        order_details_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_details_tr_num}]'
                        wait.until(EC.presence_of_element_located((By.XPATH, order_details_xpath)))
                        logging.info(f"tr[{order_details_tr_num}] 주문 상세 로드됨.")
                    except NoSuchElementException:
                        logging.info(f"tr[{order_num}] 버튼이 없습니다. 스킵.")
                        continue
                    except TimeoutException:
                        logging.error(f"tr[{order_details_tr_num}] 주문 상세 로드 실패.")
                        driver.save_screenshot(f"order_{order_num}_details_timeout.png")
                        continue
                    except Exception as e:
                        logging.error(f"tr[{order_num}] 처리 중 오류: {e}")
                        traceback.print_exc()
                        driver.save_screenshot(f"order_{order_num}_processing_error.png")
                        continue

                # 상세에서 j=1,4,7,... 최대 99
                for j in range(1, 100, 3):
                    item_name_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_details_tr_num}]/td/div/div/section[1]/div[3]/div[{j}]/span[1]/div/span[1]'
                    item_qty_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_details_tr_num}]/td/div/div/section[1]/div[3]/div[{j}]/span[1]/div/span[2]'

                    try:
                        item_name_element = driver.find_element(By.XPATH, item_name_xpath)
                        item_name = item_name_element.text.strip()

                        item_qty_element = driver.find_element(By.XPATH, item_qty_xpath)
                        item_qty_text = item_qty_element.text.strip()

                        match = re.search(r'\d+', item_qty_text.replace(',', ''))
                        if match:
                            sales_qty = int(match.group())
                        else:
                            logging.warning(f"수량 추출 실패: '{item_qty_text}'")
                            continue

                        if item_name in item_to_cell:
                            cell = item_to_cell[item_name]
                            sales_data[cell] = sales_data.get(cell, 0) + sales_qty
                            logging.info(f"[{item_name}] 수량 {sales_qty}, 셀 {cell}")
                        else:
                            logging.warning(f"매핑되지 않은 품목 [{item_name}], 수량 {sales_qty}")
                    except NoSuchElementException:
                        logging.info(f"tr[{order_details_tr_num}] j={j} 품목/수량 없으므로 중단.")
                        break
                    except Exception as e:
                        logging.error(f"tr[{order_details_tr_num}], j={j} 오류: {e}")
                        traceback.print_exc()
                        driver.save_screenshot(f"order_{order_details_tr_num}_item_{j}_error.png")
                        break

            # 다음 페이지 버튼
            try:
                next_page_button_xpath = '//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[5]/div/div[2]/span/button'
                next_page_button = driver.find_element(By.XPATH, next_page_button_xpath)
                if 'disabled' in next_page_button.get_attribute('class'):
                    logging.info("다음 페이지 없음. 종료.")
                    break
                next_page_button.click()
                logging.info("다음 페이지로 이동.")
                time.sleep(2)
            except NoSuchElementException:
                logging.info("다음 페이지 버튼 없음. 종료.")
                break
            except Exception as e:
                logging.error(f"다음 페이지 이동 중 오류: {e}")
                traceback.print_exc()
                driver.save_screenshot("next_page_error.png")
                break

        # 모든 페이지 끝 → batch_update
        if sales_data:
            batch = []
            for cell_address, qty in sales_data.items():
                batch.append({'range': cell_address, 'values': [[qty]]})
                logging.info(f"배치 업데이트 준비: {cell_address} = {qty}")
            try:
                inventory_sheet.batch_update(batch)
                logging.info("'재고' 시트 배치 업데이트 완료.")
            except Exception as e:
                logging.error(f"'재고' 시트 업데이트 오류: {e}")
                driver.save_screenshot("update_inventory_sheet_error.png")
        else:
            logging.info("판매 데이터가 없습니다.")
    except Exception as e:
        logging.error("판매 수량 추출/기록 중 오류:")
        logging.error(f"{str(e)}")
        traceback.print_exc()
        driver.save_screenshot("extract_and_update_sales_data_error.png")
        raise


# 11) 메인 함수
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
    wait = WebDriverWait(driver, 60)  # Increased timeout to 60 seconds

    try:
        # 배민 ID/PW 체크
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
        driver.save_screenshot("after_script_success.png")
        with open("after_script_success.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logging.info("스크립트 성공 후 스크린샷과 HTML 소스를 저장했습니다.")

    except Exception as e:
        logging.error("프로세스 중 오류가 발생했습니다:")
        logging.error(f"{str(e)}")
        traceback.print_exc()
    finally:
        driver.quit()
        logging.info("WebDriver를 종료했습니다.")


if __name__ == "__main__":
    main()

import os
import re
import time
import uuid
import sys
import base64
import json
import datetime
import logging
import traceback

# Selenium
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# WebDriver Manager
from webdriver_manager.chrome import ChromeDriverManager

# Google Sheets
import gspread
from gspread_formatting import CellFormat, NumberFormat, format_cell_range
from oauth2client.service_account import ServiceAccountCredentials


###############################################################################
# 환경설정 및 상수
###############################################################################
ITEM_TO_CELL = {
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


###############################################################################
# 로깅 설정
###############################################################################
def setup_logging(log_filename='script.log'):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Stream Handler (콘솔)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_formatter = logging.Formatter('%(message)s')
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)
    
    # File Handler (파일)
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)


###############################################################################
# 환경 변수 & 설정값 불러오기
###############################################################################
def get_environment_variables():
    """
    필수 환경 변수:
        - CHENGLA_BAEMIN_ID (배민 아이디)
        - CHENGLA_BAEMIN_PW (배민 비밀번호)
        - SERVICE_ACCOUNT_JSON_BASE64 (Base64 인코딩된 Google Service Account JSON)
    """
    baemin_id = os.getenv("CHENGLA_BAEMIN_ID")
    baemin_pw = os.getenv("CHENGLA_BAEMIN_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not baemin_id or not baemin_pw:
        raise ValueError("CHENGLA_BAEMIN_ID 혹은 CHENGLA_BAEMIN_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    return baemin_id, baemin_pw, service_account_json_b64


###############################################################################
# Selenium WebDriver 관리 클래스
###############################################################################
class SeleniumDriverManager:
    def __init__(self, headless=True, user_agent=None):
        self.headless = headless
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/132.0.6834.110 Safari/537.36"
        )
        self.driver = None
    
    def __enter__(self):
        options = webdriver.ChromeOptions()
        
        # (필요 시) 헤드리스 모드
        #if self.headless:
         #   options.add_argument("--headless")
        
        # 안정성 옵션
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1180,980")
        options.add_argument(f"user-agent={self.user_agent}")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--remote-debugging-port=9222")
        
        # 예시: user-data-dir (원한다면 사용)
        # unique_dir = f"/tmp/chrome-user-data-{uuid.uuid4()}"
        # options.add_argument(f"--user-data-dir={unique_dir}")

        try:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
            logging.info("WebDriver 초기화 성공")
        except WebDriverException as e:
            logging.error("WebDriver 초기화 실패")
            raise e
        
        return self.driver
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()
            logging.info("WebDriver 종료")


###############################################################################
# Google Sheets 관리 클래스
###############################################################################
class GoogleSheetsManager:
    def __init__(self, service_account_json_b64):
        """
        :param service_account_json_b64: Base64로 인코딩된 Google Service Account JSON
        """
        self.service_account_json_b64 = service_account_json_b64
        self.client = None
        self.spreadsheet = None
    
    def authenticate(self):
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        try:
            # base64 디코딩
            raw_json = base64.b64decode(self.service_account_json_b64).decode('utf-8')
            creds_dict = json.loads(raw_json)

            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
            self.client = gspread.authorize(creds)
            logging.info("Google Sheets API 인증 성공")
        except Exception as e:
            logging.error("Google Sheets API 인증 실패")
            raise e
    
    def open_spreadsheet(self, spreadsheet_name):
        if not self.client:
            raise RuntimeError("Google API 인증이 선행되어야 합니다.")
        try:
            self.spreadsheet = self.client.open(spreadsheet_name)
            logging.info(f"스프레드시트 '{spreadsheet_name}' 열기 성공")
        except Exception as e:
            logging.error(f"스프레드시트 '{spreadsheet_name}' 열기 실패")
            raise e
    
    def get_worksheet(self, sheet_name):
        if not self.spreadsheet:
            raise RuntimeError("스프레드시트를 먼저 열어야 합니다.")
        return self.spreadsheet.worksheet(sheet_name)
    
    def update_cell_value(self, worksheet, cell, value):
        try:
            worksheet.update(cell, [[value]])
            logging.info(f"{cell} 셀에 값 '{value}' 업데이트 완료")
        except Exception as e:
            logging.error(f"{cell} 셀 업데이트 실패: {e}")
            raise e
    
    def batch_clear(self, worksheet, ranges):
        try:
            worksheet.batch_clear(ranges)
            logging.info(f"다음 범위를 Clear 완료: {ranges}")
        except Exception as e:
            logging.error(f"범위 Clear 실패: {e}")
            raise e
    
    def batch_update(self, worksheet, data_list):
        try:
            worksheet.batch_update(data_list)
            logging.info("배치 업데이트 완료")
        except Exception as e:
            logging.error(f"배치 업데이트 실패: {e}")
            raise e
    
    def format_cells_number(self, worksheet, cell_range):
        try:
            fmt = CellFormat(
                numberFormat=NumberFormat(type='NUMBER', pattern='#,##0')
            )
            format_cell_range(worksheet, cell_range, fmt)
            logging.info(f"{cell_range} 범위에 숫자 형식 적용")
        except Exception as e:
            logging.error(f"셀 형식 지정 실패: {e}")
            raise e


###############################################################################
# 기능별 함수 (배민 사이트 크롤링)
###############################################################################
def login_and_close_popup(driver, wait, username, password):
    driver.get("https://self.baemin.com/")
    logging.info("배민 페이지 접속 시도")
    
    login_page_selector = "div.style__LoginWrap-sc-145yrm0-0.hKiYRl"
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, login_page_selector)))
    
    username_selector = "#root > div.style__LoginWrap-sc-145yrm0-0.hKiYRl > div > div > form > div:nth-child(1) > span > input[type=text]"
    password_selector = "#root > div.style__LoginWrap-sc-145yrm0-0.hKiYRl > div > div > form > div.Input__InputWrap-sc-tapcpf-1.kjWnKT.mt-half-3 > span > input[type=password]"
    
    driver.find_element(By.CSS_SELECTOR, username_selector).send_keys(username)
    driver.find_element(By.CSS_SELECTOR, password_selector).send_keys(password)
    
    login_button_selector = "#root > div.style__LoginWrap-sc-145yrm0-0.hKiYRl > div > div > form > button"
    driver.find_element(By.CSS_SELECTOR, login_button_selector).click()
    logging.info("로그인 버튼 클릭")
    
    popup_close_selector = ("div[id^='\\:r'] div.Container_c_rfd6_1utdzds5.OverlayFooter_b_rmnf_1slqmfa0 > div > button.TextButton_b_rmnf_1j0jumh3.c_rfd6_13ysz3p2.c_rfd6_13ysz3p0.TextButton_b_rmnf_1j0jumh6.TextButton_b_rmnf_1j0jumhb.c_rfd6_13c33de3")
    try:
        close_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, popup_close_selector)))
        close_btn.click()
        logging.info("팝업 닫기 성공")
    except TimeoutException:
        logging.info("팝업이 없거나 이미 닫힘")

def navigate_to_order_history(driver, wait):
    menu_button_selector = "#root > div > div.Container_c_rfd6_1utdzds5.MobileHeader-module__mihN > div > div > div:nth-child(1) > button"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector)))
    driver.find_element(By.CSS_SELECTOR, menu_button_selector).click()
    
    order_history_selector = "#root > div > div.frame-container.lnb-open > div.frame-aside > nav > div.MenuList-module__lZzf.LNB-module__foKc > ul:nth-child(10) > a:nth-child(1) > button"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, order_history_selector)))
    driver.find_element(By.CSS_SELECTOR, order_history_selector).click()

    time.sleep(3)
    
    date_filter_button_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.FilterContainer-module___Rxt > button"
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, date_filter_button_selector)))
    logging.info("주문내역 페이지 진입 완료")


def set_daily_filter(driver, wait):
    filter_button_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.FilterContainer-module___Rxt > button"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, filter_button_selector)))
    driver.find_element(By.CSS_SELECTOR, filter_button_selector).click()
    
    daily_filter_xpath = "//label[contains(., '일・주')]/preceding-sibling::input[@type='radio']"
    wait.until(EC.element_to_be_clickable((By.XPATH, daily_filter_xpath)))
    driver.find_element(By.XPATH, daily_filter_xpath).click()
    
    apply_button_xpath = "//button[contains(., '적용')]"
    wait.until(EC.element_to_be_clickable((By.XPATH, apply_button_xpath)))
    driver.find_element(By.XPATH, apply_button_xpath).click()

    time.sleep(3)
    logging.info("날짜 필터 '일·주' 적용 완료")


def extract_order_summary(driver, wait):
    summary_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.TotalSummary-module__sVL1 > div > div:nth-child(2) > span.TotalSummary-module__SysK > b"
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, summary_selector)))
    
    summary_text = driver.find_element(By.CSS_SELECTOR, summary_selector).text.strip()
    logging.info(f"주문 요약 데이터: {summary_text}")
    return summary_text


def extract_sales_details(driver, wait):
    sales_data = {}
    
    while True:
        for order_num in range(1, 20, 2):
            details_tr_num = order_num + 1
            order_button_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_num}]/td/div/div'
                                   
            if order_num != 1:
                try:
                    order_button = driver.find_element(By.XPATH, order_button_xpath)
                    order_button.click()
                    wait.until(
                        EC.presence_of_element_located(
                            (By.XPATH, f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{details_tr_num}]')
                        )                
                    )
                except NoSuchElementException:
                    logging.debug(f"주문 tr[{order_num}] 버튼 없음, 스킵")
                    continue
                except TimeoutException:
                    logging.warning(f"주문 상세 로드 실패 (tr[{details_tr_num}])")
                    continue
            
            for j in range(1, 100, 3):
                base_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{details_tr_num}]/td/div/div/section[1]/div[3]/div[{j}]'
                item_name_xpath = base_xpath + "/span[1]/div/span[1]"
                item_qty_xpath = base_xpath + "/span[1]/div/span[2]"
                
                try:
                    item_name = driver.find_element(By.XPATH, item_name_xpath).text.strip()
                    item_qty_text = driver.find_element(By.XPATH, item_qty_xpath).text.strip()
                    
                    match = re.search(r'\d+', item_qty_text.replace(',', ''))
                    if not match:
                        continue
                    qty = int(match.group())
                    
                    if item_name in ITEM_TO_CELL:
                        cell_address = ITEM_TO_CELL[item_name]
                        if cell_address not in sales_data:
                            sales_data[cell_address] = 0
                        sales_data[cell_address] += qty
                        logging.info(f"[{item_name}] 수량 {qty} → {cell_address}에 누적")
                except NoSuchElementException:
                    break
                except Exception as e:
                    logging.error(f"판매 상세 추출 중 오류: tr[{details_tr_num}], j={j}, {e}")
                    traceback.print_exc()
                    break
        
        next_page_xpath = '//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[5]/div/div[2]/span/button'
        try:
            next_btn = driver.find_element(By.XPATH, next_page_xpath)
            if 'disabled' in next_btn.get_attribute('class'):
                logging.info("다음 페이지 없음. 추출 종료")
                break
            # 대기 후 클릭
            wait.until(EC.element_to_be_clickable((By.XPATH, next_page_xpath)))
            next_btn.click()
            time.sleep(2)
            logging.info("다음 페이지 이동")
        except NoSuchElementException:
            logging.info("다음 페이지 버튼 없음. 추출 종료")
            break
        except Exception as e:
            logging.warning(f"다음 페이지 이동 중 예외: {e}")
            traceback.print_exc()
            break
    
    return sales_data


###############################################################################
# 메인 함수
###############################################################################
def main():
    setup_logging()
    logging.info("=== 스크립트 시작 ===")
    
    # 1) 환경 변수
    baemin_id, baemin_pw, service_account_json_b64 = get_environment_variables()
    
    # 2) Selenium
    with SeleniumDriverManager(headless=True) as driver:
        wait = WebDriverWait(driver, 30)
        try:
            # 로그인 & 팝업
            login_and_close_popup(driver, wait, baemin_id, baemin_pw)
            
            # 주문내역 & 날짜 필터
            navigate_to_order_history(driver, wait)
            set_daily_filter(driver, wait)
            
            # 요약 & 판매량
            order_summary = extract_order_summary(driver, wait)
            sales_details = extract_sales_details(driver, wait)
        except Exception as e:
            logging.error(f"에러 발생: {e}")
            traceback.print_exc()
            return
    
    # 3) Google Sheets 인증 & 열기
    sheets_manager = GoogleSheetsManager(service_account_json_b64)
    sheets_manager.authenticate()
    
    SPREADSHEET_NAME = "청라 일일/월말 정산서"
    MU_GUNG_SHEET_NAME = "무궁 청라"
    INVENTORY_SHEET_NAME = "재고"
    
    sheets_manager.open_spreadsheet(SPREADSHEET_NAME)
    mu_gung_sheet = sheets_manager.get_worksheet(MU_GUNG_SHEET_NAME)
    inventory_sheet = sheets_manager.get_worksheet(INVENTORY_SHEET_NAME)
    
    try:
        # 날짜 행에 요약 데이터 기록
        today = datetime.datetime.now()
        day = str(today.day)
        
        date_cells = mu_gung_sheet.range('U3:U33')
        day_values = [cell.value for cell in date_cells]
        
        if day in day_values:
            row_index = day_values.index(day) + 3
            target_cell = f"V{row_index}"
            
            # 빈 문자열 방지
            digits_only = re.sub(r'[^\d]', '', order_summary)
            if not digits_only:
                digits_only = "0"
            
            extracted_num = int(digits_only)
            sheets_manager.update_cell_value(mu_gung_sheet, target_cell, extracted_num)
            sheets_manager.format_cells_number(mu_gung_sheet, 'V3:V33')
        else:
            logging.warning(f"시트에 오늘({day}) 날짜를 찾을 수 없음 (U3:U33 범위)")
        
        # 재고 시트 특정 범위 삭제
        ranges_to_clear = ['E38:E45', 'P38:P45', 'AD38:AD45', 'AP38:AP45', 'BA38:BA45']
        sheets_manager.batch_clear(inventory_sheet, ranges_to_clear)
        
        # 판매 디테일 기록
        if sales_details:
            batch_data = []
            for cell_addr, qty in sales_details.items():
                batch_data.append({'range': cell_addr, 'values': [[qty]]})
            sheets_manager.batch_update(inventory_sheet, batch_data)
        else:
            logging.info("판매 수량 데이터가 없습니다.")
    
    except Exception as e:
        logging.error(f"구글 시트 처리 중 에러: {e}")
        traceback.print_exc()
    
    logging.info("=== 스크립트 종료 ===")


if __name__ == "__main__":
    main()

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
    '백골뱅이숙회': 'E45',
    '얼큰소국밥': 'P38',
    '낙지비빔밥': 'AD38',
    '낙지볶음': 'AD40',
    '낙지파전': 'AD39',
    '소고기김치전': 'P39',
    '두부제육김치': 'P40',
    '육회비빔밥': 'E42',
    '숙주갈비탕': 'E38',
    '갈비찜덮밥': 'E39',
    '육전': 'P44',
    '육회': 'E43',
    '육사시미': 'E44',
    '갈비수육': 'E40',
    '소갈비찜': 'E41',
    '소불고기': 'P42',
    '코카콜라': 'AD42',
    '스프라이트': 'AD43',
    '토닉워터': 'AD44',
    '제로콜라': 'AD41',
    '만월': 'AQ39',
    '문배술25': 'AQ40',
    '로아 화이트': 'AQ43',
    '황금보리': 'AQ38',
    '왕율주': 'AQ41',
    '왕주': 'AQ42',
    '청하': 'BB38',
    '참이슬 후레쉬': 'BB39',
    '처음처럼': 'BB40',
    '새로': 'BB42',
    '진로이즈백': 'BB41',
    '카스': 'BB43',
    '테라': 'BB44',
    '켈리': 'BB45',
    '소성주막걸리': 'AQ45'
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

# ======================================
# 안전 클릭 함수
# ======================================
def safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(0.2)
    driver.execute_script("arguments[0].click();", element)

# ======================================
# 팝업 자동 닫기
# ======================================
def close_popup_if_exists(driver):
    try:
        backdrop = driver.find_element(By.CSS_SELECTOR, 'div.Dialog_b_c9kn_3pnjmu3')
        safe_click(driver, backdrop)
        time.sleep(0.5)
        logging.info("팝업 닫기 성공")
    except NoSuchElementException:
        logging.info("팝업 없음")
    
def wait_and_click(driver, by, value, timeout=10):
    """
    element click intercepted 문제 해결용
    """
    try:
        # element가 클릭 가능할 때까지 기다림
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        # 혹시 backdrop이 덮여 있으면 사라질 때까지 대기
        WebDriverWait(driver, timeout).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='backdrop']"))
        )
        element.click()
        return True
    except Exception as e:
        logging.warning(f"[wait_and_click] 일반 클릭 실패, 자바스크립트 클릭 시도: {e}")
        try:
            element = driver.find_element(by, value)
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e2:
            logging.error(f"[wait_and_click] 자바스크립트 클릭도 실패: {e2}")
            return False




###############################################################################
# 환경 변수 & 설정값 불러오기
###############################################################################
def get_environment_variables():
    """
    필수 환경 변수:
        - SONGDO_BAEMIN_ID (배민 아이디)
        - SONGDO_BAEMIN_PW (배민 비밀번호)
        - SERVICE_ACCOUNT_JSON_BASE64 (Base64 인코딩된 Google Service Account JSON)
    """
    baemin_id = os.getenv("SONGDO_BAEMIN_ID")
    baemin_pw = os.getenv("SONGDO_BAEMIN_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not baemin_id or not baemin_pw:
        raise ValueError("SONGDO_BAEMIN_ID 혹은 SONGDO_BAEMIN_PW 환경변수가 설정되지 않았습니다.")
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
            #options.add_argument("--headless")
        
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

    time.sleep(3)

    popup_close_selector = ("#\:r2e\: > div.Container_c_qx9u_1utdzds5.OverlayFooter_b_r4ax_1slqmfa0 > div > button.TextButton_b_r4ax_1j0jumh3.c_qx9u_13ysz3p2.c_qx9u_13ysz3p0.TextButton_b_r4ax_1j0jumh6.TextButton_b_r4ax_1j0jumhb.c_qx9u_13c33de3")
    try:
        close_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, popup_close_selector)))
        close_btn.click()
        logging.info("팝업 닫기 성공")
    except TimeoutException:
        logging.info("팝업이 없거나 이미 닫힘")
        
    popup_close_selector = ("div[id^='\\:r'] div.Container_c_rfd6_1utdzds5.OverlayFooter_b_rmnf_1slqmfa0 > div > button.TextButton_b_rmnf_1j0jumh3.c_rfd6_13ysz3p2.c_rfd6_13ysz3p0.TextButton_b_rmnf_1j0jumh6.TextButton_b_rmnf_1j0jumhb.c_rfd6_13c33de3")
    try:
        close_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, popup_close_selector)))
        close_btn.click()
        logging.info("팝업 닫기 성공")
    except TimeoutException:
        logging.info("팝업이 없거나 이미 닫힘")

def navigate_to_order_history(driver, wait):
    menu_button_selector = "#root > div > div.Container_c_qx9u_1utdzds5.MobileHeader-module__Zr4m > div > div > div:nth-child(1) > button > span > span > svg"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector)))
    driver.find_element(By.CSS_SELECTOR, menu_button_selector).click()

    time.sleep(3)
    
    order_history_selector = "#root > div > div.frame-container.lnb-open > div.frame-aside > div > nav > div.LNBList-module__DDx5.LNB-module__whjk > div.Container_c_qx9u_1utdzds5 > a:nth-child(18) > button"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, order_history_selector)))
    driver.find_element(By.CSS_SELECTOR, order_history_selector).click()
    
def set_daily_filter(driver, wait):
    import logging
    import time
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By

    logging.info("날짜 필터 설정 시작")
    
    try:
        # 필터 버튼 클릭
        filter_button_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.FilterContainer-module___Rxt > button.FilterContainer-module__vSPY.FilterContainer-module__vOLM"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, filter_button_selector)))
        driver.find_element(By.CSS_SELECTOR, filter_button_selector).click()
        time.sleep(1)

        # "일・주" 라벨 클릭
        daily_filter_xpath = '//label[.//span[text()="일・주"]]'
        element = wait.until(EC.presence_of_element_located((By.XPATH, daily_filter_xpath)))
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", element)
        time.sleep(0.5)

        # '적용' 버튼 클릭
        apply_button_xpath = '//button[.//span[text()="적용"]]'
        apply_button = wait.until(EC.element_to_be_clickable((By.XPATH, apply_button_xpath)))
        driver.execute_script("arguments[0].scrollIntoView(true);", apply_button)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", apply_button)
    
        time.sleep(30000)
        logging.info("날짜 필터 '일・주' 적용 완료")
    except Exception as e:
        logging.warning(f"[set_daily_filter] 날짜 필터 적용 중 오류 발생: {e}")
        raise
                
def extract_order_summary(driver, wait):
    """
    주문내역 상단의 총 결제금액 텍스트(예: '126,000')를 읽어옵니다.
    UI 변경에 대비해 여러 CSS 셀렉터를 순차 시도합니다.
    """
    selectors = [
        "#root > div > div.frame-container > div.frame-wrap > div.frame-body > "
        "div.OrderHistoryPage-module__R0bB > div.TotalSummary-module__sVL1 > "
        "div > div:nth-child(2) > span.TotalSummary-module__SysK > b",
        "div.OrderHistoryPage-module__R0bB div.TotalSummary-module__sVL1 span.TotalSummary-module__SysK > b",
        "div.TotalSummary-module__sVL1 b",
    ]

    last_err = None
    for css in selectors:
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
            text = driver.find_element(By.CSS_SELECTOR, css).text.strip()
            if text:
                logging.info(f"주문 요약 데이터: {text}")
                return text
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"주문 요약 영역 탐색 실패. 마지막 오류: {last_err}")

# ==============================
# 주문 상세 메뉴/수량 추출
# ==============================
def extract_sales_details(driver, wait):
    """
    배민 주문내역에서
    - 주문 펼치기
    - 메뉴명 / 수량 추출
    - 페이지네이션까지 순회
    """

    price_tail_re = re.compile(r"\s*\([^)]*원\)\s*")

    def normalize_text(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    def extract_qty(text: str) -> int:
        # "1개", "2개" → 숫자만 추출
        m = re.search(r"\d+", text.replace(",", ""))
        return int(m.group()) if m else 0

    sales_data = {}

    while True:  # ===== 페이지네이션 루프 =====
        # 주문은 tr[2]부터 시작, 한 주문당 2줄 사용
        for order_base in range(2, 22, 2):  # 최대 10개 주문
            # 1번째 주문은 이미 열려있음, 이후는 펼치기
            if order_base > 2:
                toggle_xpath = (
                    f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/'
                    f'table/tbody/tr[{order_base-1}]/td[1]/div'
                )
                try:
                    btn = wait.until(EC.presence_of_element_located((By.XPATH, toggle_xpath)))
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.4)
                except Exception:
                    logging.info(f"{order_base//2}번째 주문 펼치기 실패 → continue")
                    continue

            detail_tr = order_base

            # ===== 메뉴 루프 =====
            for j in range(1, 30, 3):  # 메뉴 블럭 단위
                name_xpath = (
                    f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/'
                    f'table/tbody/tr[{detail_tr}]/td/div/div/section[1]/div[3]/div[{j}]'
                    f'/span[1]/div/span[1]'
                )
                qty_xpath = (
                    f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/'
                    f'table/tbody/tr[{detail_tr}]/td/div/div/section[1]/div[3]/div[{j}]'
                    f'/span[1]/div/span[2]'
                )

                try:
                    raw_name = driver.find_element(By.XPATH, name_xpath).text
                    raw_qty = driver.find_element(By.XPATH, qty_xpath).text
                except NoSuchElementException:
                    break

                item_name = normalize_text(price_tail_re.sub("", raw_name))
                qty = extract_qty(raw_qty)
                if qty == 0:
                    continue

                if item_name in ITEM_TO_CELL:
                    cell = ITEM_TO_CELL[item_name]
                    sales_data[cell] = sales_data.get(cell, 0) + qty
                    logging.info(f"[집계] {item_name} → {cell} +{qty}")

        # ===== 다음 페이지 =====
        try:
            next_btn = driver.find_element(
                By.XPATH,
                '//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[5]/div/div[2]/span/button'
            )
            if "disabled" in next_btn.get_attribute("class"):
                logging.info("마지막 페이지 도달")
                break

            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(1.5)
            logging.info("다음 페이지 이동")

        except NoSuchElementException:
            logging.info("페이지네이션 버튼 없음 → 종료")
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
    
    SPREADSHEET_NAME = "송도 일일/월말 정산서"
    MU_GUNG_SHEET_NAME = "송도"
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

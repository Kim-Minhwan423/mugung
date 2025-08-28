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
    '육회비빔밥': 'P43',
    '꼬리곰탕': 'E38',
    '빨간곰탕': 'E39',
    '꼬리덮밥': 'E40',
    '육전(200g)': 'P44',
    '육회(300g)': 'P42',
    '육사시미(250g)': 'P41',
    '꼬리수육': 'E41',
    '소꼬리찜': 'E42',
    '불꼬리찜': 'E43',
    '로제꼬리': 'E44',
    '꼬리구이': 'E45',
    '中': 'E46',
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
        if self.headless:
            options.add_argument("--headless")
        
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

    popup_close_selector = ("div[id^='\\:r'] div.Container_c_dogv_1utdzds5.OverlayHeader_b_dvcv_5xyph30.c_dogv_13c33de0 > div.OverlayHeader_b_dvcv_5xyph31.c_dogv_13c33de0.c_dogv_13ysz3p2.c_dogv_13ysz3p0 > div:nth-child(1) > button")
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
    menu_button_selector = "#root > div > div.Container_c_dogv_1utdzds5.MobileHeader-module__Zr4m > div > div > div:nth-child(1) > button > span > span > svg"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector)))
    driver.find_element(By.CSS_SELECTOR, menu_button_selector).click()

    time.sleep(3)
    
    order_history_selector = "#root > div > div.frame-container.lnb-open > div.frame-aside > nav > div.LNBList-module__DDx5.LNB-module__whjk > div.Container_c_dogv_1utdzds5 > a:nth-child(18) > button"
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
    
        time.sleep(3)
        logging.info("날짜 필터 '일・주' 적용 완료")
    except Exception as e:
        logging.warning(f"[set_daily_filter] 날짜 필터 적용 중 오류 발생: {e}")
        raise


def extract_order_summary(driver, wait):
    summary_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.TotalSummary-module__sVL1 > div > div:nth-child(2) > span.TotalSummary-module__SysK > b"
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, summary_selector)))
    
    summary_text = driver.find_element(By.CSS_SELECTOR, summary_selector).text.strip()
    logging.info(f"주문 요약 데이터: {summary_text}")
    return summary_text


def extract_sales_details(driver, wait):
    """
    주문 상세 테이블을 순회하며 판매수량을 집계합니다.

    포함 기능
    - 콤보 트리거(식사메뉴 1개 + 육전/육회, 일품 소꼬리 + 육전/육회) 감지
      * 다음 div(j+1)의 li[*]/div/span에서 실제 항목 문자열 추출
      * 항목 문자열 내 줄바꿈/여분 공백 제거, "(...원)" 가격 꼬리표 제거 후 파싱
      * "<기본메뉴> + 육전|육회" → 기본메뉴 + (육전→P44 | 육회→P42) 동시 누적
      * li가 "꼬리 中자로 변경"이면 E45에 수량 누적
    - 일반 매핑: ITEM_TO_CELL 기준 매핑
    - 불꼬리찜 보정: 이름에 '불꼬리찜' 포함 시 E43 기본 누적
    - 옵션 中/중 처리: 해당 아이템의 옵션블록(다음 형제 div) 텍스트에 中/중 있으면 E45 추가 누적
    - 페이지네이션 및 안정화 로깅
    """
    import re
    import logging
    import time
    import traceback
    from selenium.common.exceptions import NoSuchElementException, TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC

    # 콤보 트리거 문구
    combo_triggers = (
        "식사메뉴 1개 + 육전", "식사메뉴 1개 + 육회",
        "일품 소꼬리 + 육전", "일품 소꼬리 + 육회",
    )

    # 정규식: ( ...원 ) 가격 꼬리표 제거용
    price_tail_re = re.compile(r"\s*\([^)]*원\)\s*")
    # 공백/줄바꿈 정리
    def normalize_text(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    sales_data = {}

    while True:
        # 화면상 홀수 tr이 헤더(펼치기), 그 다음 tr이 상세
        for order_num in range(1, 20, 2):
            details_tr_num = order_num + 1
            order_button_xpath = (
                f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_num}]/td/div/div'
            )

            # 첫 주문 외에는 펼치기 클릭
            if order_num != 1:
                try:
                    order_button = wait.until(EC.presence_of_element_located((By.XPATH, order_button_xpath)))
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", order_button)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", order_button)

                    wait.until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{details_tr_num}]',
                            )
                        )
                    )
                except (NoSuchElementException, TimeoutException):
                    logging.warning(f"주문 상세 로드 실패 (tr[{details_tr_num}])")
                    continue

            # 상세 안의 품목 div들을 3칸 간격으로 순회 (이 UI 구조에 맞춤)
            for j in range(1, 100, 3):
                base_xpath = (
                    f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/'
                    f'tr[{details_tr_num}]/td/div/div/section[1]/div[3]/div[{j}]'
                )
                item_name_xpath = base_xpath + "/span[1]/div/span[1]"
                item_qty_xpath = base_xpath + "/span[1]/div/span[2]"

                try:
                    raw_item_name = driver.find_element(By.XPATH, item_name_xpath).text
                    raw_qty = driver.find_element(By.XPATH, item_qty_xpath).text

                    item_name = normalize_text(raw_item_name)
                    item_qty_text = normalize_text(raw_qty)

                    # 수량 파싱
                    m = re.search(r"\d+", item_qty_text.replace(",", ""))
                    if not m:
                        continue
                    qty = int(m.group())

                    # ==================== 콤보 처리 ====================
                    if any(trigger in item_name for trigger in combo_triggers):
                        k = 1
                        while True:
                            # 콤보 상세 li[*]
                            li_span_xpath = base_xpath + f"/following-sibling::div[1]/li[{k}]/div/span"
                            try:
                                raw_combo_text = driver.find_element(By.XPATH, li_span_xpath).text
                            except NoSuchElementException:
                                break  # li 소진

                            combo_text_norm = normalize_text(raw_combo_text)
                            # 가격 꼬리표 제거
                            combo_text = price_tail_re.sub("", combo_text_norm)

                            # 0) 콤보 옵션: 꼬리 中자로 변경 → E45
                            if "꼬리 中자로 변경" in combo_text:
                                sales_data["E45"] = sales_data.get("E45", 0) + qty
                                logging.info(f"[콤보 옵션] {raw_combo_text} → '中'(E45) {qty} 누적")
                                k += 1
                                continue

                            # 1) 일반 콤보 아이템: "<기본메뉴> + 육전|육회"
                            parts = [p.strip() for p in combo_text.split("+")]
                            if len(parts) == 2:
                                base_menu, addon = parts[0], parts[1]

                                # 기본메뉴 누적
                                if base_menu in ITEM_TO_CELL:
                                    base_cell = ITEM_TO_CELL[base_menu]
                                    sales_data[base_cell] = sales_data.get(base_cell, 0) + qty
                                    logging.info(
                                        f"[콤보] {raw_combo_text} → 기본({base_menu}:{base_cell}) {qty} 누적"
                                    )
                                else:
                                    logging.warning(
                                        f"[콤보] 기본메뉴 매핑 없음: '{base_menu}' (원문: '{raw_combo_text}')"
                                    )

                                # 추가 육전/육회 누적
                                if addon == "육전":
                                    addon_cell = "P44"
                                elif addon == "육회":
                                    addon_cell = "P42"
                                else:
                                    addon_cell = None

                                if addon_cell:
                                    sales_data[addon_cell] = sales_data.get(addon_cell, 0) + qty
                                    logging.info(
                                        f"[콤보] {raw_combo_text} → 추가({addon}:{addon_cell}) {qty} 누적"
                                    )
                                else:
                                    logging.warning(
                                        f"[콤보] 추가 항목 매핑 없음: '{addon}' (정제전: '{raw_combo_text}')"
                                    )
                            else:
                                logging.warning(
                                    f"[콤보] 예상 형식 아님: '{raw_combo_text}' → 정제후: '{combo_text}'"
                                )
                            k += 1

                        # 콤보로 처리했으면 일반 처리 중복 방지
                        continue
                    # ================= 콤보 처리 끝 =================

                    # 옵션 블록 텍스트 (다음 형제 div)
                    option_text = ""
                    option_xpath = base_xpath + "/following-sibling::div[1]"
                    try:
                        option_text = normalize_text(driver.find_element(By.XPATH, option_xpath).text)
                    except NoSuchElementException:
                        option_text = ""

                    # 1) 정확 매핑
                    mapped = False
                    if item_name in ITEM_TO_CELL:
                        cell_address = ITEM_TO_CELL[item_name]
                        sales_data[cell_address] = sales_data.get(cell_address, 0) + qty
                        mapped = True
                        logging.info(f"[일반] {item_name} → {cell_address} {qty} 누적")

                    # 2) 불꼬리찜 보정(E43)
                    if ("불꼬리찜" in item_name) and (not mapped):
                        sales_data["E43"] = sales_data.get("E43", 0) + qty
                        logging.info(f"[보정] {item_name} → 불꼬리찜(E43) {qty} 누적")

                    # 3) 불꼬리찜 옵션 中/중 → E45 추가
                    if ("불꼬리찜" in item_name) and (("中" in option_text) or ("중" in option_text)):
                        sales_data["E45"] = sales_data.get("E45", 0) + qty
                        logging.info(
                            f"[옵션] {item_name} 옵션[{option_text}] → '中'(E45) {qty} 추가 누적"
                        )

                except NoSuchElementException:
                    # 더 이상 아이템 div가 없으면 다음 주문으로 이동
                    break
                except Exception as e:
                    logging.error(f"판매 상세 추출 중 오류: tr[{details_tr_num}], j={j}, {e}")
                    traceback.print_exc()
                    break

        # ===== 페이지네이션 =====
        next_page_xpath = (
            '//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[5]/div/div[2]/span/button'
        )
        try:
            next_btn = driver.find_element(By.XPATH, next_page_xpath)
            if "disabled" in next_btn.get_attribute("class"):
                logging.info("다음 페이지 없음. 추출 종료")
                break

            wait.until(EC.element_to_be_clickable((By.XPATH, next_page_xpath)))
            driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", next_btn)

            time.sleep(1.2)
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

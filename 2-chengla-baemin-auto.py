#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
# 설정 (필요시 수정)
###############################################################################
SPREADSHEET_NAME = "청라 일일/월말 정산서"
MU_GUNG_SHEET_NAME = "청라"
INVENTORY_SHEET_NAME = "재고"

# 청라 시트의 요약 컬럼 (기본: V=금액, W=주문수, X=판매합계(개수) )
SUMMARY_AMOUNT_COL = "V"
SUMMARY_ORDER_COUNT_COL = "W"
SUMMARY_ITEM_COUNT_COL = "X"

# 재고 시트에서 초기 클리어할 범위 (기본값: 기존 스크립트와 동일)
RANGES_TO_CLEAR = ['E38:E45', 'P38:P45', 'AD38:AD45', 'AP38:AP45', 'BA38:BA45']

# 메뉴명 -> 셀 매핑 (기존)
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
    '中': 'E45',
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
    # 콘솔
    if not logger.handlers:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        stream_formatter = logging.Formatter('%(message)s')
        stream_handler.setFormatter(stream_formatter)
        logger.addHandler(stream_handler)
    # 파일
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_formatter)
    # 중복 추가 방지
    has_file = any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    if not has_file:
        logger.addHandler(file_handler)

###############################################################################
# 안전 클릭 함수
###############################################################################
def safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(0.2)
    driver.execute_script("arguments[0].click();", element)

def wait_and_click(driver, by, value, timeout=10):
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
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

def close_popup_if_exists(driver):
    try:
        backdrop = driver.find_element(By.CSS_SELECTOR, 'div.Dialog_b_c9kn_3pnjmu3')
        safe_click(driver, backdrop)
        time.sleep(0.5)
        logging.info("팝업 닫기 성공")
    except NoSuchElementException:
        logging.info("팝업 없음")

###############################################################################
# 환경 변수 불러오기
###############################################################################
def get_environment_variables():
    baemin_id = os.getenv("CHENGLA_BAEMIN_ID")
    baemin_pw = os.getenv("CHENGLA_BAEMIN_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not baemin_id or not baemin_pw:
        raise ValueError("CHENGLA_BAEMIN_ID 혹은 CHENGLA_BAEMIN_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    return baemin_id, baemin_pw, service_account_json_b64

###############################################################################
# Selenium WebDriver Manager
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
        #if self.headless:
        #    options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1180,980")
        options.add_argument(f"user-agent={self.user_agent}")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--remote-debugging-port=9222")
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
# Google Sheets Manager
###############################################################################
class GoogleSheetsManager:
    def __init__(self, service_account_json_b64):
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
        """
        data_list: [{'range': 'E38', 'values': [[qty]]}, ...]
        """
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
# 배민 크롤링 관련 함수
###############################################################################
def login_and_close_popup(driver, wait, username, password):
    driver.get("https://self.baemin.com/")
    logging.info("배민 페이지 접속 시도")
    # 기존 셀렉터 기반 로그인 (기존 스크립트 참조)
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

    # 팝업 닫기 시도 (여러 케이스)
    popup_close_selector = ("div[id^='\\:r'] div.Container_c_c1xs_1utdzds5.OverlayFooter_b_c9kn_1slqmfa0 > div > button.TextButton_b_c9kn_1j0jumh3.c_c1xs_13ysz3p2.c_c1xs_13ysz3p0.TextButton_b_c9kn_1j0jumh6.TextButton_b_c9kn_1j0jumhb.c_c1xs_13c33de3")
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
        logging.info("팝업 닫기 성공 (케이스2)")
    except TimeoutException:
        logging.info("팝업이 없거나 이미 닫힘 (케이스2)")

def navigate_to_order_history(driver, wait):
    menu_button_selector = "#root > div > div.Container_c_c1xs_1utdzds5.MobileHeader-module__Zr4m > div > div > div:nth-child(1) > button > span > span > svg"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector)))
    driver.find_element(By.CSS_SELECTOR, menu_button_selector).click()
    time.sleep(3)
    order_history_selector = "#root > div > div.frame-container.lnb-open > div.frame-aside > nav > div.LNBList-module__DDx5.LNB-module__whjk > div.Container_c_c1xs_1utdzds5 > a:nth-child(18) > button"
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, order_history_selector)))
    driver.find_element(By.CSS_SELECTOR, order_history_selector).click()
    logging.info("주문내역 메뉴로 이동")

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

def extract_sales_details(driver, wait):
    """
    주문 상세 테이블을 순회하며 판매수량을 집계합니다.
    반환: (sales_data_dict, order_count, total_item_qty)
      - sales_data_dict: {셀주소: qty, ...}
      - order_count: 읽은 주문(행) 수
      - total_item_qty: 모든 아이템의 수량 합계
    """
    combo_triggers = (
        "식사메뉴 1개 + 육전", "식사메뉴 1개 + 육회",
        "일품 소꼬리 + 육전", "일품 소꼬리 + 육회"
    )
    price_tail_re = re.compile(r"\s*\([^)]*원\)\s*")

    def scrape_order_detail(driver, order_index):
    """
    특정 주문(order_index번째)을 펼치고 메뉴 dict 반환
    """
    results = {}
    try:
        # 주문 펼치기
        order_row = driver.find_element(
            By.XPATH,
            f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/table/tbody/tr[{order_index}]/td[1]/div'
        )
        driver.execute_script("arguments[0].click();", order_row)
        time.sleep(1)

        # 메뉴 반복 (N=2,5,8,...)
        for N in range(2, 30, 3):  # 최대 10개 메뉴까지
            try:
                name_xpath = f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/table/tbody/tr[{order_index+1}]/td/div/div/section[1]/div[3]/div[{N}]/li[1]/div/span'
                qty_xpath  = f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/table/tbody/tr[{order_index+1}]/td/div/div/section[1]/div[3]/div[{N}]/li[2]/div/span'

                item_name = driver.find_element(By.XPATH, name_xpath).text.strip()
                qty_text  = driver.find_element(By.XPATH, qty_xpath).text.strip()
                qty = int(re.sub(r'[^0-9]', '', qty_text) or "0")

                if item_name:
                    # "中" 옵션은 따로 분류
                    if "中" in item_name:
                        results["__중옵션__"] = results.get("__중옵션__", 0) + qty
                    else:
                        results[item_name] = results.get(item_name, 0) + qty
            except:
                break  # 더 이상 메뉴 없으면 종료

    except Exception as e:
        logging.warning(f"{order_index}번째 주문 크롤링 실패: {e}")

    return results


def scrape_all_orders(driver, max_pages=5):
    """
    여러 페이지 돌면서 주문 크롤링
    """
    all_results = {}
    order_count = 0
    total_item_qty = 0

    for page in range(max_pages):
        for idx in range(2, 12):  # tr[2]~tr[11] = 최대 5 주문
            data = scrape_order_detail(driver, idx)
            if not data:
                continue
            order_count += 1
            for k, v in data.items():
                if k == "__중옵션__":
                    all_results["E46"] = all_results.get("E46", 0) + v
                elif k in ITEM_TO_CELL:
                    all_results[ITEM_TO_CELL[k]] = all_results.get(ITEM_TO_CELL[k], 0) + v
                total_item_qty += v

        # TODO: 페이지네이션 처리 필요 시 여기에 클릭 로직 추가
        try:
            next_btn_xpath = '//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[5]/div/div[2]/span/button'
            next_btn = driver.find_element(By.XPATH, next_btn_xpath)
            if "disabled" not in next_btn.get_attribute("class"):
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(1.5)
                logging.info("다음 페이지 이동")
            else:
                break
        except NoSuchElementException:
            break

    return all_results, order_count, total_item_qty


    def normalize_text(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    sales_data = {}
    order_count = 0
    total_item_qty = 0

    # 주문 tr[2]부터 tr[12]까지 (최대 6번째 주문)
    for order_index in range(2, 12, 2):
        # 첫 주문은 기본 열림, 이후 주문은 펼치기 클릭
        if order_index > 2:
            toggle_xpath = (
                f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/table/tbody/tr[{order_index}]/td/div'
            )
            try:
                btn = wait.until(EC.presence_of_element_located((By.XPATH, toggle_xpath)))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)
            except Exception:
                logging.info(f"{order_index//2}번째 주문 펼치기 실패 → break")
                break

        # 주문 하나 읽음
        order_count += 1

        # 주문 내 메뉴 아이템 수집
        for j in range(1, 101, 3):  # j=1,4,7,10,...100
            item_name_xpath = (
                f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/table/tbody/tr[{order_index}]'
                f'/td/div/div/section[1]/div[3]/div[{j}]/span[1]/div/span[1]'
            )
            item_qty_xpath = (
                f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/table/tbody/tr[{order_index}]'
                f'/td/div/div/section[1]/div[3]/div[{j}]/span[1]/div/span[2]'
            )

            try:
                raw_name = driver.find_element(By.XPATH, item_name_xpath).text
                raw_qty = driver.find_element(By.XPATH, item_qty_xpath).text
            except NoSuchElementException:
                break

            item_name = normalize_text(price_tail_re.sub("", raw_name))
            qty_match = re.search(r"\d+", raw_qty.replace(",", ""))
            if not qty_match:
                continue
            qty = int(qty_match.group())
            total_item_qty += qty

            # 콤보 처리
            if any(trigger in item_name for trigger in combo_triggers):
                k = 1
                while True:
                    li_xpath = (
                        f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/table/tbody/tr[{order_index}]'
                        f'/td/div/div/section[1]/div[3]/div[{j}]/following-sibling::div[1]/li[{k}]/div/span'
                    )
                    try:
                        raw_combo = driver.find_element(By.XPATH, li_xpath).text
                    except NoSuchElementException:
                        break

                    combo_text = normalize_text(price_tail_re.sub("", raw_combo))
                    parts = [p.strip() for p in combo_text.split("+")]
                    if len(parts) == 2:
                        base_menu, addon = parts
                        if base_menu in ITEM_TO_CELL:
                            sales_data[ITEM_TO_CELL[base_menu]] = sales_data.get(ITEM_TO_CELL[base_menu], 0) + qty
                        addon_cell = "P44" if addon == "육전" else "P42" if addon == "육회" else None
                        if addon_cell:
                            sales_data[addon_cell] = sales_data.get(addon_cell, 0) + qty
                    k += 1
                continue

            # 일반 매핑
            if item_name in ITEM_TO_CELL:
                cell = ITEM_TO_CELL[item_name]
                sales_data[cell] = sales_data.get(cell, 0) + qty
                logging.info(f"[일반] {item_name} → {cell} {qty}")

            # 불꼬리찜 특수 처리
            if "불꼬리찜" in item_name:
                sales_data["E43"] = sales_data.get("E43", 0) + qty
                option_xpath = (
                    f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/table/tbody/tr[{order_index}]'
                    f'/td/div/div/section[1]/div[3]/div[{j}]/following-sibling::div[1]'
                )
                try:
                    option_text = driver.find_element(By.XPATH, option_xpath).text
                    if "中" in option_text or "중" in option_text:
                        sales_data["E46"] = sales_data.get("E46", 0) + qty
                except NoSuchElementException:
                    pass

            # 모든 메뉴 공통 '중' 옵션 처리
            option_xpath = (
                f'//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[4]/div/div/table/tbody/tr[{order_index}]'
                f'/td/div/div/section[1]/div[3]/div[{j}]/following-sibling::div[1]'
            )
            try:
                option_text = driver.find_element(By.XPATH, option_xpath).text
                if "中" in option_text or "중" in option_text:
                    sales_data["E46"] = sales_data.get("E46", 0) + qty
            except NoSuchElementException:
                pass

    # 페이지네이션(다음 버튼 클릭하여 추가 페이지 읽는 로직 필요시 확장)
    try:
        next_btn_xpath = '//*[@id="root"]/div/div[2]/div[3]/div[1]/div[4]/div[5]/div/div[2]/span/button'
        next_btn = driver.find_element(By.XPATH, next_btn_xpath)
        if "disabled" not in next_btn.get_attribute("class"):
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(1.5)
            logging.info("다음 페이지 이동 (주의: 현재는 한 페이지당 최대 6주문만 처리하도록 설계됨)")
    except NoSuchElementException:
        logging.info("다음 페이지 버튼 없음 → 종료")

    return sales_data, order_count, total_item_qty

###############################################################################
# 메인
###############################################################################
def main():
    setup_logging()
    logging.info("=== 스크립트 시작 ===")

    # 1) 환경 변수
    try:
        baemin_id, baemin_pw, service_account_json_b64 = get_environment_variables()
    except Exception as e:
        logging.error(f"환경변수 로드 실패: {e}")
        return

    # 2) Selenium으로 배민 접속/데이터 수집
    sales_details = {}
    order_summary_text = "0"
    order_count = 0
    total_item_qty = 0

    try:
        with SeleniumDriverManager(headless=True) as driver:
            wait = WebDriverWait(driver, 30)
            try:
                login_and_close_popup(driver, wait, baemin_id, baemin_pw)
                navigate_to_order_history(driver, wait)
                set_daily_filter(driver, wait)
                order_summary_text = extract_order_summary(driver, wait)
                sales_details, order_count, total_item_qty = scrape_all_orders(driver, max_pages=5)
            except Exception as e:
                logging.error(f"크롤링 중 에러 발생: {e}")
                traceback.print_exc()
                return
    except Exception as e:
        logging.error(f"WebDriver 오류: {e}")
        traceback.print_exc()
        return

    # 3) Google Sheets 인증 & 업데이트
    try:
        sheets_manager = GoogleSheetsManager(service_account_json_b64)
        sheets_manager.authenticate()
        sheets_manager.open_spreadsheet(SPREADSHEET_NAME)
        mu_gung_sheet = sheets_manager.get_worksheet(MU_GUNG_SHEET_NAME)
        inventory_sheet = sheets_manager.get_worksheet(INVENTORY_SHEET_NAME)
    except Exception as e:
        logging.error(f"구글 시트 인증/열기 실패: {e}")
        traceback.print_exc()
        return

    try:
        # --- 3-1) 청라 시트: 날짜 위치 찾고 요약(금액/주문수/판매합계) 기록 ---
        today = datetime.datetime.now()
        day = str(today.day)
        date_cells = mu_gung_sheet.range('U3:U33')
        day_values = [cell.value for cell in date_cells]

        if day in day_values:
            row_index = day_values.index(day) + 3
            amount_cell = f"{SUMMARY_AMOUNT_COL}{row_index}"
            order_count_cell = f"{SUMMARY_ORDER_COUNT_COL}{row_index}"
            item_count_cell = f"{SUMMARY_ITEM_COUNT_COL}{row_index}"

            # 금액 숫자만 추출 (문자열 예: '126,000원' 혹은 '126,000')
            digits_only = re.sub(r'[^\d]', '', order_summary_text)
            if not digits_only:
                digits_only = "0"
            extracted_amount = int(digits_only)

            # 업데이트 (덮어쓰기)
            sheets_manager.update_cell_value(mu_gung_sheet, amount_cell, extracted_amount)
            sheets_manager.update_cell_value(mu_gung_sheet, order_count_cell, order_count)
            sheets_manager.update_cell_value(mu_gung_sheet, item_count_cell, total_item_qty)

            # 포맷 적용 (금액/숫자)
            sheets_manager.format_cells_number(mu_gung_sheet, f"{SUMMARY_AMOUNT_COL}3:{SUMMARY_AMOUNT_COL}33")
            sheets_manager.format_cells_number(mu_gung_sheet, f"{SUMMARY_ORDER_COUNT_COL}3:{SUMMARY_ORDER_COUNT_COL}33")
            sheets_manager.format_cells_number(mu_gung_sheet, f"{SUMMARY_ITEM_COUNT_COL}3:{SUMMARY_ITEM_COUNT_COL}33")

            logging.info(f"청라 시트 요약 업데이트: 금액 {amount_cell}={extracted_amount}, 주문수 {order_count_cell}={order_count}, 판매개수 {item_count_cell}={total_item_qty}")
        else:
            logging.warning(f"시트에 오늘({day}) 날짜를 찾을 수 없음 (U3:U33 범위)")

        # --- 3-2) 재고 시트: 특정 범위 클리어 후 매핑된 셀에 판매 수량 기록 ---
        sheets_manager.batch_clear(inventory_sheet, RANGES_TO_CLEAR)

        if sales_details:
            batch_data = []
            # sales_details은 {셀주소: qty}
            for cell_addr, qty in sales_details.items():
                batch_data.append({'range': cell_addr, 'values': [[qty]]})
            if batch_data:
                sheets_manager.batch_update(inventory_sheet, batch_data)
                # 숫자 형식 적용
                cell_ranges = [cell_addr for cell_addr in sales_details.keys()]
                for cell_addr in cell_ranges:
                    sheets_manager.format_cells_number(inventory_sheet, cell_addr)
                logging.info("재고 시트 판매 수량 업데이트 완료")
        else:
            logging.info("판매 데이터가 없어 재고 시트 업데이트 없음")

    except Exception as e:
        logging.error(f"구글 시트 업데이트 중 에러: {e}")
        traceback.print_exc()
        return

    logging.info("=== 스크립트 종료 ===")

if __name__ == "__main__":
    main()

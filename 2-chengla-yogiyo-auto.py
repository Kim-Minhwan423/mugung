import os
import sys
import re
import time
import datetime
import logging
import traceback
import base64
import json
import uuid        # [추가]
import tempfile    # [추가]

# -----------------------------
# Selenium
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
    ElementClickInterceptedException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# WebDriver Manager
from webdriver_manager.chrome import ChromeDriverManager

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

###############################################################################
# 1. 로깅 설정
###############################################################################
def setup_logging(log_filename='script.log'):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 콘솔 로그
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_formatter = logging.Formatter('%(message)s')
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)
    
    # 파일 로그
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

###############################################################################
# 2. 환경 변수 불러오기 (서비스 계정 JSON에서 spreadsheet_id 추출하지 않음)
###############################################################################
def get_environment_variables():
    """
    필수 환경 변수:
      - YOGIYO_ID (요기요 아이디)
      - YOGIYO_PW (요기요 비밀번호)
      - SERVICE_ACCOUNT_JSON_BASE64 (Base64 인코딩된 Google Service Account JSON)
    """
    yogiyo_id = os.getenv("YOGIYO_ID")
    yogiyo_pw = os.getenv("YOGIYO_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")
    
    if not yogiyo_id or not yogiyo_pw:
        raise ValueError("YOGIYO_ID 혹은 YOGIYO_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")
    
    return yogiyo_id, yogiyo_pw, service_account_json_b64

###############################################################################
# 3. Chrome 드라이버 세팅 (고유 프로필 사용)
###############################################################################
def get_chrome_driver(use_profile=False):
    chrome_options = webdriver.ChromeOptions()
    # chrome_options.add_argument("--headless")  # 필요시 주석 해제
    
    # User-Agent 변경
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/110.0.5481.77 Safari/537.36"
    )
    
    if use_profile:
        unique_id = uuid.uuid4()
        user_data_dir = os.path.join(tempfile.gettempdir(), f"chrome_profile_{unique_id}")
        os.makedirs(user_data_dir, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        logging.info(f"[use_profile=True] 고유 Chrome 프로필 경로: {user_data_dir}")
    
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1029,657")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # 웹드라이버 탐지 방지 스크립트
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        }
    )
    logging.info("ChromeDriver 초기화 성공")
    return driver

###############################################################################
# 4. 요기요 로그인 및 페이지 이동
###############################################################################
def login_yogiyo(driver, yogiyo_id, yogiyo_pw):
    driver.get("https://ceo.yogiyo.co.kr/self-service-home/")
    logging.info("요기요 사장님 사이트 로그인 페이지 접속 완료")
    
    id_selector = "#root > div > div.LoginLayout__Container-sc-1dkvjmn-1.cFYxDO > div > div.Login__Container-sc-11eppm3-0.hruuNe > form > div:nth-child(1) > div > div.sc-fEOsli.iqThlJ > div.sc-bjUoiL.LLOzV > input"
    pw_selector = "#root > div > div.LoginLayout__Container-sc-1dkvjmn-1.cFYxDO > div > div.Login__Container-sc-11eppm3-0.hruuNe > form > div:nth-child(2) > div > div.sc-fEOsli.iqThlJ > div.sc-bjUoiL.LLOzV > input"
    login_btn_selector = "#root > div > div.LoginLayout__Container-sc-1dkvjmn-1.cFYxDO > div > div.Login__Container-sc-11eppm3-0.hruuNe > form > button"
    
    try:
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, id_selector)))
        driver.find_element(By.CSS_SELECTOR, id_selector).send_keys(yogiyo_id)
        logging.info("아이디 입력")
        driver.find_element(By.CSS_SELECTOR, pw_selector).send_keys(yogiyo_pw)
        logging.info("비밀번호 입력")
        driver.find_element(By.CSS_SELECTOR, login_btn_selector).click()
        logging.info("로그인 버튼 클릭")
    except TimeoutException:
        logging.warning("로그인 페이지 로딩 Timeout")
    time.sleep(5)

def close_popup_if_exist(driver):
    popup_close_selector = "#portal-root > div > div > div.FullScreenModal__Header-sc-7lyzl-1.eQqjUi > svg"
    try:
        close_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, popup_close_selector))
        )
        close_btn.click()
        logging.info("팝업 닫기 완료")
    except TimeoutException:
        logging.info("팝업이 나타나지 않음(혹은 이미 닫힘)")

def go_store_selector(driver):
    store_selector = "#root > div > div.CommonLayout__UnderHeader-sc-f8yrrc-2.feAuQx "
    "> div.LNB__Container-sc-1eyat45-17.gDEqtO.LNB__StyledLNB-sc-1eyat45-19.PQgEK "
    "> div.LNB__StoreSelectorWrapper-sc-1eyat45-1.ikrGtG > div > div.StoreSelector__Wrapper-sc-1rowjsb-15.lkBMGb"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, store_selector)))
        driver.find_element(By.CSS_SELECTOR, store_selector).click()
        logging.info("스토어 셀렉터 버튼 클릭")
    except TimeoutException:
        logging.warning("스토어 셀렉터 버튼을 찾지 못함")
    time.sleep(3)  # 화면 로딩 대기

def go_chengla_selector(driver):
    chengla_selector = "#root > div > div.CommonLayout__UnderHeader-sc-f8yrrc-2.feAuQx "
    "> div.LNB__Container-sc-1eyat45-17.gDEqtO.LNB__StyledLNB-sc-1eyat45-19.PQgEK > div.LNB__StoreSelectorWrapper-sc-1eyat45-1.ikrGtG "
    "> div > div.Container-sc-1snjxcp-0.iEgpIZ > ul > li:nth-child(2) > ul > li"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, chengla_selector)))
        driver.find_element(By.CSS_SELECTOR, chengla_selector).click()
        logging.info("무궁 청라점 버튼 클릭")
    except TimeoutException:
        logging.warning("무궁 청라점 버튼을 찾지 못함")
    time.sleep(3)  # 화면 로딩 대기

def go_order_history(driver):
    """
    주문내역 메뉴 클릭
    """
    order_btn_selector = "#root > div > div.CommonLayout__UnderHeader-sc-f8yrrc-2.feAuQx "
    "> div.LNB__Container-sc-1eyat45-17.gDEqtO.LNB__StyledLNB-sc-1eyat45-19.PQgEK > div.LNB__ScrollWrapper-sc-1eyat45-16.fHssYu "
    "> div.LNB__QuickMenu-sc-1eyat45-2.hGHFDR > button.LNB__MenuButton-sc-1eyat45-3.flLQfy"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, order_btn_selector)))
        driver.find_element(By.CSS_SELECTOR, order_btn_selector).click()
        logging.info("주문내역 버튼 클릭")
    except TimeoutException:
        logging.warning("주문내역 버튼을 찾지 못함")
    time.sleep(3)  # 주문내역 화면 로딩 대기
    
###############################################################################
# 5. 주문 상세 정보 추출 (주문금액 및 품목명/수량)
###############################################################################
def get_first_10_rows_text(driver):
    """
    주문내역 페이지에서 tbody 내 1~10번 행의 텍스트를 가져와 출력합니다.
    날짜 비교 없이 단순히 행 텍스트만 확인하는 예시.
    """
    rows_data = {}
    for i in range(1, 11):
        row_selector = (
            f"#common-layout-wrapper-id > div.CommonLayout__Contents-sc-f8yrrc-1.fWTDpk > div > div > "
            "div.CardListLayout__CardListContainer-sc-26whdp-0.jofZaF.CardListLayout__StyledCardListLayout-sc-26whdp-1.lgKFYo > "
            "div > div.TitleContentCard__CardContentLayout-sc-1so7oge-0.fwXwFk > div > div > div > "
            f"div.Table__Container-sc-s3p2z0-0.efwKvR > table > tbody > tr:nth-child({i})"
        )
        try:
            row_elem = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, row_selector))
            )
            row_text = row_elem.text.strip()
            rows_data[i] = row_text
            logging.info(f"Row {i} text: {row_text}")
        except TimeoutException:
            logging.warning(f"Row {i} 행을 찾지 못함 (주문 건수가 10개 미만이거나 다른 문제)")
        except Exception as e:
            logging.error(f"Row {i} 추출 중 오류: {e}")
    
    return rows_data

###############################################################################
# 6. Google Sheets 업데이트 함수
###############################################################################
def update_google_sheets(total_order_amount, aggregated_products):
    """
    - "청라 일일/월말 정산서" 스프레드시트의 "무궁 청라" 시트에서 U3:U33(날짜)와 W3:W33(주문 총액)을 업데이트
    - "재고" 시트의 지정 범위를 클리어한 후, 미리 정의한 매핑에 따라 각 품목의 수량을 업데이트
    """
    # 서비스 계정 JSON 디코딩 및 인증
    yogiyo_id, yogiyo_pw, service_account_json_b64 = get_environment_variables()
    service_account_json = base64.b64decode(service_account_json_b64)
    service_account_info = json.loads(service_account_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scopes)
    gc = gspread.authorize(creds)
    
    # 스프레드시트 이름을 직접 사용 (spreadsheet_id 사용 안함)
    sh = gc.open("청라 일일/월말 정산서")
    
    # 1. "무궁 청라" 시트 업데이트 (일일 정산)
    sheet_daily = sh.worksheet("무궁 청라")
    date_values = sheet_daily.get("U3:U33")
    today_day = str(datetime.datetime.today().day)
    row_index = None
    for i, row in enumerate(date_values, start=3):
        if row and row[0].strip() == today_day:
            row_index = i
            break
    if row_index:
        cell = f"W{row_index}"
        sheet_daily.update_acell(cell, total_order_amount)
        logging.info(f"무궁 청라 시트 {cell}에 오늘 주문 총액 {total_order_amount} 업데이트")
    else:
        logging.warning("오늘 날짜에 해당하는 셀을 무궁 청라 시트에서 찾지 못함")
    
    # 2. "재고" 시트 업데이트
    sheet_inventory = sh.worksheet("재고")
    clear_ranges = ["F38:F45", "Q38:Q45", "AE38:AF45", "AQ38:AQ45", "BB38:BB45"]
    sheet_inventory.batch_clear(clear_ranges)
    
    update_mapping = {
        '육회비빔밥(1인분)': 'Q43', 
        '꼬리곰탕(1인분)': 'F38', 
        '빨간곰탕(1인분)': 'F39', 
        '꼬리덮밥(1인분)': 'F40', 
        '육전(200g)': 'Q44', 
        '육회(300g)': 'Q42', 
        '육사시미(250g)': 'Q41', 
        '꼬리수육(2인분)': 'F41', 
        '소꼬리찜(2인분)': 'F42', 
        '불꼬리찜(2인분)': 'F43', 
        '로제꼬리(2인분)': 'F44', 
        '꼬리구이(2인분)': 'F45', 
        '코카콜라': 'AE42', 
        '스프라이트': 'AE43', 
        '토닉워터': 'AE44', 
        '제로콜라': 'AE41', 
        '만월 360ml': 'AQ39', 
        '문배술25 375ml': 'AQ40', 
        '로아 화이트 350ml': 'AQ43', 
        '황금보리 375ml': 'AQ38', 
        '왕율주 360ml': 'AQ41', 
        '왕주 375ml': 'AQ42', 
        '청하': 'BB38', 
        '참이슬': 'BB39', 
        '처음처럼': 'BB40', 
        '새로': 'BB42', 
        '진로이즈백': 'BB41', 
        '카스': 'BB43', 
        '테라': 'BB44', 
        '켈리': 'BB45', 
        '소성주': 'AQ45'
    }
    
    batch_updates = []
    for product, cell in update_mapping.items():
        qty = aggregated_products.get(product, 0)
        batch_updates.append({
            "range": cell,
            "values": [[qty]]
        })
    if batch_updates:
        sheet_inventory.batch_update(batch_updates)
        logging.info("재고 시트 업데이트 완료")

###############################################################################
# 메인 실행 흐름
###############################################################################
def main():
    setup_logging("script.log")
    yogiyo_id, yogiyo_pw, service_account_json_b64 = get_environment_variables()
    driver = get_chrome_driver(use_profile=True)
    try:
        # 1. 로그인 및 초기 팝업 처리
        login_yogiyo(driver, yogiyo_id, yogiyo_pw)
        close_popup_if_exist(driver)
        
        # 2. 다시 홈페이지로 이동 (go_store_selector 전에)
        driver.get("https://ceo.yogiyo.co.kr/self-service-home/")
        time.sleep(3)  # 페이지 로딩 대기
        
        # 3. 스토어 선택, 청라점 진입 및 주문내역 진입
        go_store_selector(driver)
        go_chengla_selector(driver)
        go_order_history(driver)
        
        # 4. 오늘 주문 처리 (주문금액 및 품목 정보 집계)
        
        # 5. Google Sheets 업데이트 (일일 정산 및 재고)
        update_google_sheets(total_order, product_quantities)
    
    except Exception as e:
        logging.error(f"에러 발생: {e}")
        traceback.print_exc()
    finally:
        driver.quit()
        logging.info("WebDriver 종료")

if __name__ == "__main__":
    main()

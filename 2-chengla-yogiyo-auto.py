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
def extract_order_details(driver):
    """
    팝업창에서 판매 총 금액과 판매 품목명 및 갯수를 추출합니다.
    
    판매 총 금액은 아래 셀렉터를 사용합니다.
      #portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > div > 
      div:nth-child(1) > div > li > div.OrderDetailPopup__OrderDeliveryFee-sc-cm3uu3-6.kCCvPa
      
    판매 품목은 i번째 제품마다 다음과 같이 추출합니다.
      - i번째 제품명: 
        #portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > div > 
        div:nth-child(2) > div > div > div.OrderDetailPopup__OrderFeeListItem-sc-cm3uu3-10.gEOrSU > 
        div:nth-child(i) > div.OrderDetailPopup__OrderFeeItemContent-sc-cm3uu3-14.jDwgnm > span:nth-child(1)
      - i번째 수량:
        #portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > div > 
        div:nth-child(2) > div > div > div.OrderDetailPopup__OrderFeeListItem-sc-cm3uu3-10.gEOrSU > 
        div:nth-child(i) > div.OrderDetailPopup__OrderFeeItemContent-sc-cm3uu3-14.jDwgnm > span:nth-child(1)
    """
    total_fee = 0
    products = {}
    try:
        # 판매 총 금액 추출 (콤마 제거 후 정수형으로 변환)
        fee_selector = (
            "#portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > div > "
            "div:nth-child(1) > div > li > div.OrderDetailPopup__OrderDeliveryFee-sc-cm3uu3-6.kCCvPa"
        )
        fee_elem = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, fee_selector))
        )
        fee_text = fee_elem.text  # 예: "123,456"
        fee_clean = re.sub(r"[^\d]", "", fee_text)  # 숫자만 남김
        total_fee = int(fee_clean) if fee_clean else 0
        logging.info(f"추출된 판매 총 금액: {total_fee}")
        
        # 판매 품목 데이터 추출: i번째 제품을 순차적으로 확인 (더 이상 없으면 종료)
        i = 1
        while True:
            try:
                # i번째 제품명 셀렉터
                product_name_selector = (
                    f"#portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > div > "
                    f"div:nth-child(2) > div > div > div.OrderDetailPopup__OrderFeeListItem-sc-cm3uu3-10.gEOrSU > "
                    f"div:nth-child({i}) > div.OrderDetailPopup__OrderFeeItemContent-sc-cm3uu3-14.jDwgnm > span:nth-child(1)"
                )
                product_name_elem = driver.find_element(By.CSS_SELECTOR, product_name_selector)
                product_name = product_name_elem.text.strip()
                
                # i번째 수량 셀렉터
                qty_selector = (
                    f"#portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > div > "
                    f"div:nth-child(2) > div > div > div.OrderDetailPopup__OrderFeeListItem-sc-cm3uu3-10.gEOrSU > "
                    f"div:nth-child({i}) > div.OrderDetailPopup__OrderFeeItemContent-sc-cm3uu3-14.jDwgnm > span:nth-child(1)"
                )
                try:
                    qty_elem = driver.find_element(By.CSS_SELECTOR, qty_selector)
                    qty_text = qty_elem.text.strip()
                    qty_clean = re.sub(r"[^\d]", "", qty_text)
                    product_qty = int(qty_clean) if qty_clean else 1
                except Exception:
                    product_qty = 1  # 수량 정보가 없으면 기본값 1
                
                products[product_name] = products.get(product_name, 0) + product_qty
                logging.info(f"추출된 품목 {i}: {product_name} - {product_qty}")
                i += 1
            except Exception:
                # 더 이상 i번째 제품이 존재하지 않으면 종료
                break
    except Exception as e:
        logging.error(f"주문 상세 정보 추출 오류: {e}")
    
    return total_fee, products


def process_orders_for_today(driver):
    """
    주문 목록 페이지에서 날짜 셀의 텍스트가 오늘 날짜(월.일 형식, 예: 02.01)와 일치하는 주문 셀을
    하나씩 클릭하여 팝업으로부터 판매 총 금액 및 품목 데이터를 추출합니다.
    
    또한, 페이지 하단의 페이지 네비게이션(li:nth-child(2), li:nth-child(3) 등)을 통해
    다음 페이지가 존재하면 계속해서 데이터를 가져옵니다.
    """
    aggregated_total = 0
    aggregated_products = {}
    
    # 오늘 날짜를 MM.DD 형식으로 생성 (예: "02.01")
    today_str = datetime.datetime.now().strftime("%m.%d")
    logging.info(f"오늘 날짜 (MM.DD): {today_str}")
    
    page = 1
    while True:
        logging.info(f"페이지 {page} 처리 시작")
        # 주문 테이블의 모든 행(tr) 선택
        orders_rows_selector = (
            "#common-layout-wrapper-id > div.CommonLayout__Contents-sc-f8yrrc-1.fWTDpk > div > div > "
            "div.CardListLayout__CardListContainer-sc-26whdp-0.jofZaF.CardListLayout__StyledCardListLayout-sc-26whdp-1.lgKFYo > "
            "div > div.TitleContentCard__CardContentLayout-sc-1so7oge-0.fwXwFk > div > div > div > "
            "div.Table__Container-sc-s3p2z0-0.efwKvR > table > tbody > tr"
        )

        try:
            orders = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, orders_rows_selector))
            )
        except TimeoutException:
            logging.warning("주문 테이블을 찾지 못함")
            break
        
        logging.info(f"페이지 {page}의 주문 건수: {len(orders)}")
        
        # 각 주문 행 처리
        for index, order_row in enumerate(orders, start=1):
            try:
                # 각 주문 행 내 날짜 셀 선택 (날짜는 "MM.DD(요일)" 형식)
                date_cell = order_row.find_element(
                    By.CSS_SELECTOR,
                    "td.Table__Td-sc-s3p2z0-6.PaginationTableBody__CustomTd-sc-17ibl0-3.qnuqu.hylTlX > div"
                )
                date_text = date_cell.text.strip()  # 예: "02.01(토)"
                # 정규표현식으로 "MM.DD" 부분만 추출
                match = re.match(r"(\d{2}\.\d{2})", date_text)
                if match:
                    order_date = match.group(1)
                else:
                    logging.warning(f"날짜 형식 불일치: {date_text}")
                    continue
                
                logging.info(f"주문 {index}의 날짜: {order_date}")
                
                # 오늘 날짜와 일치하는 주문인 경우
                if order_date != today_str:
                    continue
                
                # 주문 행 클릭 (스크롤하여 보이게 한 후 클릭)
                driver.execute_script("arguments[0].scrollIntoView(true);", order_row)
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable(order_row))
                order_row.click()
                logging.info(f"주문 {index} (날짜: {order_date}) 클릭")
                time.sleep(2)  # 팝업 로딩 대기
                
                # 팝업에서 상세 정보 추출
                fee, products = extract_order_details(driver)
                aggregated_total += fee
                for prod, qty in products.items():
                    aggregated_products[prod] = aggregated_products.get(prod, 0) + qty
                
                # 팝업 닫기 (셀렉터: #portal-root > ... > svg > g > rect)
                close_popup_selector = (
                    "#portal-root > div > div > div.FullScreenModal__Header-sc-7lyzl-1.eQqjUi > svg > g > rect"
                )
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, close_popup_selector))
                ).click()
                logging.info(f"주문 {index} 팝업 닫기 완료")
                time.sleep(1)
            except Exception as e:
                logging.error(f"주문 {index} 처리 오류: {e}")
                continue
        
        # 페이지 하단의 페이지 네비게이션을 확인하여 다음 페이지가 있는지 체크
        try:
            pagination_container_selector = (
                "#common-layout-wrapper-id > div.CommonLayout__Contents-sc-f8yrrc-1.fWTDpk > div > div > "
                "div.CardListLayout__CardListContainer-sc-26whdp-0.jofZaF.CardListLayout__StyledCardListLayout-sc-26whdp-1.lgKFYo > "
                "div > div.TitleContentCard__CardContentLayout-sc-1so7oge-0.fwXwFk > div > div > div > "
                "div.Pagination__Container-sc-iw43f5-3.jMWkBM > ul"
            )
            pagination_ul = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, pagination_container_selector))
            )
            # 다음 페이지 버튼: li:nth-child(현재 페이지 + 1)
            next_page_selector = f"li:nth-child({page+1})"
            next_page_elem = pagination_ul.find_element(By.CSS_SELECTOR, next_page_selector)
            driver.execute_script("arguments[0].scrollIntoView(true);", next_page_elem)
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, next_page_selector))
            )
            next_page_elem.click()
            logging.info(f"페이지 {page+1}로 이동")
            time.sleep(2)  # 페이지 전환 대기
            page += 1
        except Exception:
            logging.info("더 이상 다음 페이지가 없거나 이동에 실패")
            break
    
    return aggregated_total, aggregated_products

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
        total_order, product_quantities = process_orders_for_today(driver)
        logging.info(f"오늘 주문 총액: {total_order}, 제품별 수량: {product_quantities}")
        
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

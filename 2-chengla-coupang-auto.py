import os
import sys
import re
import time
import datetime
import logging
import traceback
import base64
import json
import random

# Selenium & Undetected Chromedriver
import undetected_chromedriver as uc  # 🚨 중요: pip install undetected-chromedriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains  # 🚨 마우스 이동용
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    WebDriverException
)

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.auth.exceptions import TransportError

###############################################################################
# 1. 로깅 설정
###############################################################################
def open_google_sheet_with_retry(client, sheet_name, retries=5):
    for attempt in range(1, retries + 1):
        try:
            doc = client.open(sheet_name)
            return doc
        except Exception as e:
            print(f"[경고] 구글 시트 연결 실패 (시도 {attempt}/{retries}) → {e}")
            time.sleep(random.uniform(1.2, 2.4))
    raise RuntimeError(f"구글 시트 연결 실패: {sheet_name}")

def setup_logging(log_filename='script.log'):
    logger = logging.getLogger()
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_formatter = logging.Formatter('%(message)s')
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

###############################################################################
# 2. 환경 변수 불러오기
###############################################################################
def get_environment_variables():
    coupang_id = os.getenv("CHENGLA_COUPANG_ID")
    coupang_pw = os.getenv("CHENGLA_COUPANG_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not coupang_id or not coupang_pw:
        raise ValueError("CHENGLA_COUPANG_ID 혹은 CHENGLA_COUPANG_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    return coupang_id, coupang_pw, service_account_json_b64

###############################################################################
# 3. Undetected Chrome 드라이버 세팅 (완벽 우회)
###############################################################################
def get_chrome_driver():
    options = uc.ChromeOptions()

    # 독립된 새 전용 프로필 사용
    temp_profile = os.path.join(os.getcwd(), "chrome_profile")
    options.add_argument(f"--user-data-dir={temp_profile}")

    # 백그라운드(화면 없이) 실행이 필요한 환경인 경우 아래 주석(#)을 해제하세요.
    # 일반 headless는 쿠팡이 바로 알아챕니다. 최신 --headless=new를 사용해야 안전합니다.
    # options.add_argument("--headless=new") 

    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # 한국어 브라우저 설정
    options.add_argument("--lang=ko-KR")

    try:
        # 🚨 version_main을 제거하여 uc가 내 컴퓨터 크롬 버전을 자동으로 잡게 합니다.
        driver = uc.Chrome(options=options)
    except Exception as e:
        logging.error(f"Undetected Chrome 초기화 실패: {e}")
        logging.info("기본 크롬 드라이버로 전환을 시도합니다...")
        
        # 만약 uc가 환경 문제로 죽는다면 예비책으로 기본 selenium 드라이버 작동
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        options.add_argument("--disable-blink-features=AutomationControlled")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

    logging.info("Chrome 실행 완료 (자동화 우회 활성화)")
    return driver
###############################################################################
# 4. 쿠팡이츠 로그인 & 팝업 닫기 (사람처럼 행동하기 적용)
###############################################################################
def human_type(element, text):
    """사람이 키보드를 직접 타이핑하는 것처럼 글자별로 무작위 지연을 주는 함수"""
    element.clear()
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.08, 0.22)) # 사람이 타이핑하는 평균 속도

def human_click(driver, element):
    """마우스를 진짜 버튼 위로 이동시킨 후 물리적으로 클릭하는 함수"""
    try:
        action = ActionChains(driver)
        action.move_to_element(element).perform() # 마우스 커서 이동
        time.sleep(random.uniform(0.3, 0.7))      # 이동 후 타겟 인지 대기 시간
        element.click()
    except:
        driver.execute_script("arguments[0].click();", element) # 실패 시 예비책

def login_coupang_eats(driver, user_id, password):
    driver.get("https://store.coupangeats.com/merchant/login")
    logging.info("쿠팡이츠 상점 로그인 페이지 접속 완료")
    time.sleep(random.uniform(2.1, 3.8)) # 로딩 후 자연스러운 대기

    # 아이디 입력 (사람처럼)
    username_input = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#loginId"))
    )
    human_type(username_input, user_id)
    logging.info("아이디 입력 완료")
    time.sleep(random.uniform(0.8, 1.6))

    # 비밀번호 입력 (사람처럼)
    password_input = driver.find_element(By.CSS_SELECTOR, "#password")
    human_type(password_input, password)
    logging.info("비밀번호 입력 완료")
    time.sleep(random.uniform(1.1, 2.3))

    max_login_attempts = 3
    for attempt in range(1, max_login_attempts + 1):
        try:
            login_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    "#merchant-login > div > div.center-form > div > div > div > form > button"))
            )
            
            # 물리적 마우스 이동 및 클릭 시뮬레이션
            human_click(driver, login_button)
            logging.info(f"로그인 버튼 클릭 (시도 {attempt}/{max_login_attempts})")
            time.sleep(2.5)

            # 🚨 [추가 수정] 비밀번호 밑에 빨간색 에러 문구가 떴는지 실시간으로 검사
            try:
                error_elements = driver.find_elements(By.CSS_SELECTOR, "form p, .error-message, .error-txt, [class*='error']")
                for err_el in error_elements:
                    if err_el.is_displayed() and err_el.text.strip():
                        err_text = err_el.text.strip()
                        logging.error(f"❌ [쿠팡이츠 로그인 거부]: {err_text}")
                        raise RuntimeError(f"쿠팡 사이트 로그인 에러 발생: {err_text}")
            except RuntimeError:
                raise # 에러 발생 시 즉시 프로세스 탈출
            except:
                pass # 에러가 보이지 않는다면 패스

            # URL이 변경될 때까지 대기
            WebDriverWait(driver, 8).until(
                lambda d: "management" in d.current_url and "login" not in d.current_url
            )
            
            logging.info(f"현재 URL: {driver.current_url}")
            logging.info("로그인 성공 확인, 매출관리 이동중...")
            time.sleep(random.uniform(2, 3))

            driver.get("https://store.coupangeats.com/merchant/management")
            logging.info("매출관리 메인 강제 이동 완료")
            time.sleep(random.uniform(1.5, 2.5))
            return

        except TimeoutException:
            logging.warning(f"로그인 후 주소 전환 대기 시간 초과 (시도 {attempt} 실패)")
            if attempt == max_login_attempts:
                raise RuntimeError("쿠팡이츠 로그인 연속 실패: 계정 권한 문제 또는 정지 상태 가능성")
            time.sleep(random.uniform(3.0, 5.0))

def close_coupang_popup(driver):
    popup_selectors = [
        "#merchant-onboarding-body > div.dialog-modal-wrapper.ezi9xs118.css-1g106yu.e1gf2dph0 > div > div > div > div.css-rucxuz.ezi9xs112 > div",
        "#merchant-onboarding-body > div.dialog-modal-wrapper.e462wnt15.css-1252kk2.e1gf2dph0 > div > div > div > div > div.css-2bi7a5.e462wnt4 > div",
        "#merchant-onboarding-body > div.dialog-modal-wrapper.css-g20w7n.e1gf2dph0 > div > div > div > button"
    ]

    for idx, selector in enumerate(popup_selectors, start=1):
        try:
            logging.info(f"[팝업{idx}] 클릭 시도")
            element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(random.uniform(1.2, 2.4))
            
            # 팝업도 물리적 클릭 시도
            human_click(driver, element)
            logging.info(f"[팝업{idx}] 클릭 성공")
            time.sleep(random.uniform(1.2, 2.4))
        except TimeoutException:
            logging.info(f"[팝업{idx}] 없음 또는 클릭 불가 → 스킵")
        except Exception as e:
            logging.info(f"[팝업{idx}] 예외 발생 → {e}")

    # 매출관리 버튼
    try:
        order_management_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#merchant-management > div > nav > div.css-hd12du.esf794x2 > ul > li:nth-child(5) > a")
            )
        )
        human_click(driver, order_management_button)
        logging.info("매출관리 버튼 클릭")
        time.sleep(random.uniform(1.5, 2.8))
    except TimeoutException:
        logging.info("매출관리가 나타나지 않아 스킵")

    # 펼쳐보기 버튼
    try:
        float_dropdown_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#merchant-management > div > div > div.management-scroll > div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > div > div > div > div > div.mt-4.sales-search-row > div.sales-search-filters-date-picker.css-18vw3vd.e4pgcj010 > div > div > svg")
            )
        )
        human_click(driver, float_dropdown_button)
        logging.info("펼쳐보기 버튼 클릭")
        time.sleep(random.uniform(1.2, 2.4))
    except TimeoutException:
        logging.info("펼처보기가 나타나지 않아 스킵")

###############################################################################
# 5. '오늘' 버튼 + '조회' 버튼
###############################################################################
def click_today_and_search(driver):
    try:
        today_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "#merchant-management > div > div > div.management-scroll > "
                "div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > "
                "div > div > div > div > div.mt-4.sales-search-row > div.sales-search-filters-date-picker.css-18vw3vd.e4pgcj010 > "
                "div > div.css-mc9tgf.e4pgcj05 > div.css-h5a8xm.e4pgcj04 > span:nth-child(1) > label > svg"
            ))
        )
        human_click(driver, today_button)
        logging.info("오늘 버튼 클릭")
        time.sleep(random.uniform(1.2, 2.4))
    except TimeoutException:
        logging.warning("오늘 버튼을 찾지 못했습니다.")

    try:
        search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "#merchant-management > div > div > div.management-scroll > "
                "div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > div > div > div > div > "
                "div.mt-4.sales-search-row > div.sales-search-filters-date-picker.css-18vw3vd.e4pgcj010 > button"
            ))
        )
        human_click(driver, search_button)
        logging.info("조회 버튼 클릭")
        time.sleep(random.uniform(1.5, 2.8))
    except TimeoutException:
        logging.warning("조회 버튼을 찾지 못했습니다.")

###############################################################################
# 6. 매출액 추출
###############################################################################
def get_today_revenue(driver):
    revenue_selector = (
        "#merchant-management > div > div > div.management-scroll > "
        "div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > "
        "div > div > div > div > div.summary-wrapper > div > "
        "div.body-txt.summary-row > div.h1-txt > span:nth-child(1)"
    )
    try:
        revenue_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, revenue_selector))
        )
    except TimeoutException:
        logging.warning("매출액 요소를 찾지 못했습니다.")
        return 0

    revenue_text = revenue_element.text
    logging.info(f"조회된 매출액 텍스트: {revenue_text}")

    cleaned = revenue_text.replace(",", "").replace("원", "").strip()
    try:
        revenue_int = int(cleaned)
        logging.info(f"매출액(정수) = {revenue_int}")
        return revenue_int
    except ValueError:
        logging.warning(f"매출액 변환 실패, 문자열 그대로 반환: {revenue_text}")
        return 0

###############################################################################
# 7. 주문 목록 스크래핑
###############################################################################
def expand_and_parse_order(driver, order_index):
    expand_selector = (
        "#merchant-management > div > div > div.management-scroll > "
        "div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > "
        "div > div > div > div > div:nth-child(5) > "
        f"div > ul.order-search-result-content.row > li:nth-child({order_index}) > "
        "section.order-item.row.text-nowrap > div.order-price.col-4.col-md-3.text-right > button"
    )

    expand_btn = None
    try:
        expand_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, expand_selector))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", expand_btn)
        time.sleep(random.uniform(1.0, 2.0))

        human_click(driver, expand_btn)
        logging.info(f"{order_index}번째 주문 펼치기 버튼 클릭 성공")

    except TimeoutException:
        logging.warning(f"{order_index}번째 주문 펼치기 버튼을 찾지 못했습니다.")
        return []
    except ElementClickInterceptedException:
        if expand_btn:
            try:
                time.sleep(random.uniform(0.5, 1.5))
                driver.execute_script("arguments[0].click();", expand_btn)
            except WebDriverException:
                return []
        return []
    except WebDriverException:
        return []

    time.sleep(random.uniform(1.2, 2.4))  
    return parse_expanded_order(driver)

def parse_expanded_order(driver):
    try:
        expanded_section = driver.find_element(
            By.CSS_SELECTOR, "li.col-12.expanded section.order-details.initial-order-detail"
        )
    except NoSuchElementException:
        logging.warning("펼쳐진 주문 섹션을 찾지 못했습니다.")
        return []

    item_elements = expanded_section.find_elements(
        By.CSS_SELECTOR, "div.order-detail-list > div > div.col-12.col-md-9 > ul > li"
    )

    results = []
    for idx, item_el in enumerate(item_elements, start=1):
        try:
            name_el = item_el.find_element(By.CSS_SELECTOR, "div > div:nth-child(1)")
            qty_el = item_el.find_element(By.CSS_SELECTOR, "div > div.col-2.text-nowrap")

            raw_name = name_el.text.strip()
            lines = raw_name.split('\n')
            item_name = lines[0]
            item_qty = qty_el.text.strip()

            results.append((item_name, item_qty))
            logging.info(f"  - ({idx}) 품목명='{item_name}', 판매량='{item_qty}'")
        except Exception as e:
            logging.warning(f"  - ({idx})번 아이템 파싱 실패: {e}")

    return results

def scrape_orders_in_page(driver):
    all_items = []
    for i in range(1, 11):  
        items = expand_and_parse_order(driver, i)
        if items:
            all_items.extend(items)
    return all_items

def scrape_all_pages_by_buttons(driver):
    all_data = []
    current_page = 1

    while True:
        logging.info(f"\n=== [PAGE {current_page}] ===")
        items_in_this_page = scrape_orders_in_page(driver)
        all_data.extend(items_in_this_page)

        next_page = current_page + 1
        success = go_to_page_button(driver, next_page)
        if not success:
            logging.info(f"{next_page}페이지 버튼이 없어 종료")
            break

        current_page = next_page
        time.sleep(random.uniform(1.5, 3.0))

    return all_data

def go_to_page_button(driver, page_number):
    if page_number == 1:
        return True

    nth = page_number + 2  
    selector = (
        "#merchant-management > div > div > div.management-scroll > "
        "div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > "
        "div > div > div > div > div:nth-child(5) > div > div > div > div > ul > "
        f"li:nth-child({nth}) > button"
    )

    try:
        page_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
        )
        human_click(driver, page_btn)
        logging.info(f"{page_number}페이지 버튼 클릭 성공")
        time.sleep(random.uniform(1.5, 2.8)) 

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.order-search-result-content.row"))
        )
        logging.info(f"{page_number}페이지 로딩 완료")
        return True
    except TimeoutException:
        logging.info(f"{page_number}페이지 버튼 클릭 실패 또는 존재하지 않음")
        return False

###############################################################################
# 8. 구글 시트
###############################################################################
def get_gspread_client_from_b64(service_account_json_b64):
    json_bytes = base64.b64decode(service_account_json_b64)
    json_str = json_bytes.decode('utf-8')
    json_keyfile = json.loads(json_str)

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json_keyfile, scope)
    client = gspread.authorize(creds)
    return client

def update_jaego_sheet(jaego_sheet, item_cell_map, item_quantity_map):
    ranges_to_clear = ["G38:G45", "R38:R45", "AI38:AI45", "AT38:AT45", "BE38:BE45"]
    try:
        jaego_sheet.batch_clear(ranges_to_clear)
        logging.info(f"[재고] 범위 초기화: {ranges_to_clear}")
    except Exception as e:
        logging.warning(f"[재고] 범위 초기화 실패: {e}")

    batch_updates = []
    for item_name, qty in item_quantity_map.items():
        if item_name not in item_cell_map:
            logging.info(f"[재고] 매핑 없는 아이템 '{item_name}' -> 스킵")
            continue
        cell_addr = item_cell_map[item_name]
        batch_updates.append({
            'range': cell_addr,
            'values': [[qty]]
        })

    if not batch_updates:
        logging.info("[재고] 업데이트할 아이템이 없습니다.")
        return

    try:
        jaego_sheet.batch_update(batch_updates)
        logging.info(f"[재고] 총 {len(batch_updates)}개 셀에 수량 배치 업데이트 완료")
    except Exception as e:
        logging.error(f"[재고] 배치 업데이트 중 오류: {e}")

def update_revenue_by_day(mugeung_sheet, revenue):
    date_in_e1 = mugeung_sheet.acell('E1').value
    if not date_in_e1:
        logging.warning("[청라] E1에 날짜가 없습니다.")
        return

    day_str = date_in_e1.split("-")[-1]
    try:
        day_str = str(int(day_str))
    except ValueError:
        logging.warning(f"[청라] E1({date_in_e1})에서 일자 추출 실패.")
        return

    date_cells = mugeung_sheet.range('U3:U33')
    found = False
    for cell in date_cells:
        if cell.value == day_str:
            row_num = cell.row
            mugeung_sheet.update_cell(row_num, 24, revenue)
            logging.info(f"[청라] E1={date_in_e1} -> day={day_str}, X{row_num}={revenue}")
            found = True
            break

    if not found:
        logging.warning(f"[청라] U열에서 일자 {day_str}를 찾지 못했습니다.")

###############################################################################
# 9. 메인 실행 흐름
###############################################################################
def main():
    setup_logging('script.log')

    coupang_id, coupang_pw, service_account_json_b64 = get_environment_variables()
    driver = get_chrome_driver()
    all_order_items = []
    today_revenue = 0

    try:
        # 1) 로그인
        login_coupang_eats(driver, user_id=coupang_id, password=coupang_pw)
        close_coupang_popup(driver)

        # 2) 오늘/조회
        click_today_and_search(driver)

        # 3) 매출액
        today_revenue = get_today_revenue(driver)
        logging.info(f"[결과] 오늘 매출액: {today_revenue}")

        # 4) 주문 스크래핑
        all_order_items = scrape_all_pages_by_buttons(driver)
        logging.info(f"[결과] 수집된 메뉴 아이템 총 {len(all_order_items)}개")

    except Exception as e:
        logging.error(f"에러 발생: {e}")
        traceback.print_exc()

    finally:
        if 'driver' in locals():
            driver.quit()
            logging.info("WebDriver 종료")

    # 5) 구글 시트 연동
    try:
        client = get_gspread_client_from_b64(service_account_json_b64)
        doc = open_google_sheet_with_retry(client, "청라 일일/월말 정산서")
        mugeung_sheet = doc.worksheet("청라")
        jaego_sheet = doc.worksheet("재고")

        update_revenue_by_day(mugeung_sheet, today_revenue)

        item_cell_map = {
            '백골뱅이숙회': 'G45', '얼큰소국밥': 'R38', '낙지비빔밥': 'AI38', '낙지볶음': 'AI40',
            '낙지파전': 'AI39', '우삼겹김치전': 'R39', '두부김치제육': 'R40', '육회비빔밥': 'G42',
            '숙주갈비탕': 'G38', '갈비찜덮밥': 'G39', '육전': 'R44', '육회': 'G43', '육사시미': 'G44',
            '갈비수육': 'G40', '소갈비찜': 'G41', '코카콜라 355ml': 'AI42', '스프라이트 355ml': 'AI43',
            '토닉워터 300ml': 'AI44', '제로콜라 355ml': 'AI41', '만월 360ml': 'AT39',
            '문배술25 375ml': 'AT40', '배도가 로아 화이트 350ml': 'AT43', '황금보리 375ml': 'AT38',
            '사곡양조 왕율주 360ml': 'AT41', '왕주 375ml': 'AT42', '청하 300ml': 'BE38',
            '참이슬 후레쉬 360ml': 'BE39', '처음처럼 360ml': 'BE40', '새로 360ml': 'BE42',
            '진로이즈백 360ml': 'BE41', '카스 500ml': 'BE43', '테라 500ml': 'BE44',
            '캘리 500ml': 'BE45', '소성주 750ml': 'AT45'
        }

        item_quantity_map = {}
        for (item_name, qty_text) in all_order_items:
            m = re.search(r"(\d+)", qty_text)
            qty_num = int(m.group(1)) if m else 1
            name_for_map = item_name.strip()
            item_quantity_map[name_for_map] = item_quantity_map.get(name_for_map, 0) + qty_num

        update_jaego_sheet(jaego_sheet, item_cell_map, item_quantity_map)

    except Exception as e:
        logging.error(f"구글 시트 연동 에러: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()

import os
import sys
import re
import time
import datetime
import logging
import traceback
import base64
import json

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

# -----------------------------
# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

###############################################################################
# 1. 로깅 설정
###############################################################################
def setup_logging(log_filename='script.log'):
    """
    로그를 콘솔+파일에 동시에 남기는 설정.
    """
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
# 2. 환경 변수 & 설정값 불러오기
###############################################################################
def get_environment_variables():
    """
    필수 환경 변수:
        - CHENGLA_COUPANG_ID (쿠팡 아이디)
        - CHENGLA_COUPANG_PW (쿠팡 비밀번호)
        - SERVICE_ACCOUNT_JSON_BASE64 (Base64 인코딩된 Google Service Account JSON)
    """
    coupang_id = os.getenv("CHENGLA_COUPANG_ID")
    coupang_pw = os.getenv("CHENGLA_COUPANG_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not coupang_id or not coupang_pw:
        raise ValueError("CHENGLA_COUPANG_ID 혹은 CHENGLA_COUPANG_PW 환경 변수가 설정되지 않았습니다.")

    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경 변수가 설정되지 않았습니다.")

    return coupang_id, coupang_pw, service_account_json_b64

###############################################################################
# 2-1. Selenium 드라이버 세팅
###############################################################################
def get_chrome_driver(use_profile=False):
    """
    ChromeDriver를 초기화한 뒤, 여러 옵션(봇 차단 방지, 프로필 재사용 등) 적용.
    """
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/110.0.5481.77 Safari/537.36"
    )

    # 프로필 재사용 (로그인 유지, 쿠키 활용)
    if use_profile:
        user_data_dir = r"C:\Users\day9b\AppData\Local\Google\Chrome\User Data"
        if os.path.exists(user_data_dir):
            chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
            chrome_options.add_argument("--profile-directory=Default")
            logging.info("기존 Chrome 프로필 재사용 중...")
        else:
            logging.warning("지정한 프로필 경로가 존재하지 않습니다. 새 프로필이 사용됩니다.")

    # 자동화 감지 해제 옵션
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,960")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # CDP를 통한 webdriver 감지 속성 제거
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """
        }
    )

    logging.info("ChromeDriver 초기화 성공")
    return driver

###############################################################################
# 3. 쿠팡이츠 로그인 & 팝업 닫기
###############################################################################
def login_coupang_eats(driver, user_id, password):
    """
    1) 쿠팡이츠 관리자 페이지 로그인
    2) 팝업 (2개) 닫기
    3) 매출관리 버튼 클릭
    4) 펼쳐보기 버튼 클릭 (있으면)
    """
    driver.get("https://store.coupangeats.com/merchant/login")
    logging.info("쿠팡이츠 상점 로그인 페이지 접속 완료")
    time.sleep(2)

    # 아이디 입력
    username_input = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#loginId"))
    )
    username_input.clear()
    username_input.send_keys(user_id)
    logging.info("아이디 입력")

    # 비밀번호 입력
    password_input = driver.find_element(By.CSS_SELECTOR, "#password")
    password_input.clear()
    password_input.send_keys(password)
    logging.info("비밀번호 입력")

    # 로그인 버튼 클릭
    login_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "#merchant-login > div > div.center-form > div > div > div > form > button")
        )
    )
    login_button.click()
    logging.info("로그인 버튼 클릭")
    time.sleep(2)

    # 팝업 1
    try:
        popup_close1 = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "#merchant-onboarding-body > div.dialog-modal-wrapper.css-1pi72m7.e1gf2dph0 > div > div > div > button"
            ))
        )
        popup_close1.click()
        logging.info("팝업1 닫기 완료")
    except TimeoutException:
        logging.info("팝업1이 나타나지 않아 스킵")

    # 팝업 2
    try:
        popup_close2 = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "#merchant-onboarding-body > div.dialog-modal-wrapper.css-g20w7n.e1gf2dph0 > div > div > div > button"
            ))
        )
        popup_close2.click()
        logging.info("팝업2 닫기 완료")
    except TimeoutException:
        logging.info("팝업2가 나타나지 않아 스킵")

    time.sleep(1)

    # 매출관리 버튼
    try:
        order_management_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#merchant-management > div > nav > div.css-8pnkb2.esf794x2 > ul > li:nth-child(5) > a")
            )
        )
        order_management_button.click()
        logging.info("매출관리 버튼 클릭")
    except TimeoutException:
        logging.info("매출관리가 나타나지 않아 스킵")

    # 펼쳐보기 버튼
    try:
        float_dropdown_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#merchant-management > div > div > div.management-scroll > div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > div > div > div > div > div.mt-4.sales-search-row > div.sales-search-filters > div > div.dropdown-btn.highlight > i")
            )
        )
        float_dropdown_button.click()
        logging.info("펼쳐보기 버튼 클릭")
    except TimeoutException:
        logging.info("펼처보기가 나타나지 않아 스킵")

###############################################################################
# 4. '오늘' 버튼 + '조회' 버튼
###############################################################################
def click_today_and_search(driver):
    """
    '오늘' 라디오 버튼 & '조회' 버튼 순차 클릭
    """
    # 오늘 버튼
    # 조회 버튼
    try:
        search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "#merchant-management > div > div > div.management-scroll > "
                "div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > div > div > div > div > "
                "div.mt-4.sales-search-row > div.sales-search-filters > button"
            ))
        )
        search_button.click()
        logging.info("조회 버튼 클릭")
    except TimeoutException:
        logging.warning("조회 버튼을 찾지 못했습니다.")

    time.sleep(2)

###############################################################################
# 5. 매출액 추출
###############################################################################
def get_today_revenue(driver):
    """
    상단 매출액 텍스트 추출 -> 콤마, '원' 제거 -> int 변환
    """
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
# 6. 주문 목록 스크래핑 (페이지 버튼 이동, 무한)
###############################################################################
def expand_and_parse_order(driver, order_index):
    """
    order_index번째 주문의 '펼치기' 버튼을 클릭한 뒤, 상세 파싱.
    - 클릭 시 화면 겹침이 있으면 스크롤+JS 클릭 재시도.
    - 실패 시 [] 반환 (주문만 스킵).
    """
    expand_selector = (
        "#merchant-management > div > div > div.management-scroll > "
        "div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > "
        "div > div > div > div > div:nth-child(5) > "
        f"div > ul.order-search-result-content.row > li:nth-child({order_index}) > "
        "section.order-item.row.text-nowrap > div.order-price.col-4.col-md-3.text-right > button"
    )

    try:
        # 버튼 대기
        expand_btn = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, expand_selector))
        )

        # 스크롤
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", expand_btn)
        time.sleep(0.5)

        # 클릭 시도
        expand_btn.click()
        logging.info(f"{order_index}번째 주문 펼치기 버튼 클릭 성공")

    except (ElementClickInterceptedException, WebDriverException) as e:
        # 인터셉트나 기타 클릭 오류 -> JS 클릭 재시도
        logging.info(f"{order_index}번째 주문 일반 클릭 실패: {e}")
        logging.info("-> JS 클릭 재시도")
        try:
            driver.execute_script("arguments[0].click();", expand_btn)
        except WebDriverException as e2:
            logging.warning(f"{order_index}번째 주문 JS 클릭도 실패: {e2}")
            return []

    except TimeoutException:
        logging.warning(f"{order_index}번째 주문 펼치기 버튼을 찾지 못했습니다.")
        return []
    except Exception as e:
        logging.warning(f"{order_index}번째 주문 버튼 대기 중 오류: {e}")
        return []

    time.sleep(1)
    return parse_expanded_order(driver)

def parse_expanded_order(driver):
    """
    펼쳐진 주문 섹션에서 '메뉴명, 판매량'을 파싱.
    - 옵션이 줄바꿈(\n) 형태이면 첫 줄만 취함.
    """
    from selenium.common.exceptions import NoSuchElementException

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
            item_name = lines[0]  # 첫 줄만

            item_qty = qty_el.text.strip()
            results.append((item_name, item_qty))
            logging.info(f"  - ({idx}) 품목명='{item_name}', 판매량='{item_qty}'")

        except Exception as e:
            logging.warning(f"  - ({idx})번 아이템 파싱 실패: {e}")

    return results

def scrape_orders_in_page(driver):
    """
    현재 페이지에서 1~10번째 주문을 펼쳐 파싱.
    펼치기 실패 시 해당 주문만 스킵, 나머지 계속.
    """
    all_items = []
    for i in range(1, 11):
        items = expand_and_parse_order(driver, i)
        if items:  # []이면 스킵
            all_items.extend(items)
    return all_items

def go_to_page_button(driver, page_number):
    """
    페이지 번호 'page_number'를 누르는 버튼 클릭.
    - page=1 -> 이미 접속 상태라고 가정 -> 클릭 스킵
    - page=2 -> li:nth-child(4)
    - page=3 -> li:nth-child(5)
    - page=4 -> li:nth-child(6)
    ...
    성공 시 True, 실패 시 False
    """
    if page_number == 1:
        return True  # 1페이지는 이미 로딩된 상태

    nth = page_number + 2  # 예: page=2 -> li:nth-child(4)
    selector = (
        "#merchant-management > div > div > div.management-scroll > "
        "div.management-page.p-2.p-md-4.p-lg-5.d-flex.flex-column > "
        "div > div > div > div > div:nth-child(5) > div > div > div > div > ul > "
        f"li:nth-child({nth}) > button"
    )
    try:
        page_btn = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
        )
        page_btn.click()
        logging.info(f"{page_number}페이지 버튼 클릭 성공")
        time.sleep(1)
        return True
    except TimeoutException:
        logging.info(f"{page_number}페이지 버튼을 찾지 못했습니다.")
        return False

def scrape_all_pages_by_buttons(driver):
    """
    1페이지 -> 2페이지 -> 3페이지 ... 
    페이지 버튼이 없을 때까지 '무한'으로 스크래핑.
    """
    all_data = []
    current_page = 1

    while True:
        # 현재 페이지 스크래핑
        logging.info(f"\n=== [PAGE {current_page}] ===")
        items_in_this_page = scrape_orders_in_page(driver)
        all_data.extend(items_in_this_page)

        # 다음 페이지 버튼 클릭 시도
        next_page = current_page + 1
        success = go_to_page_button(driver, next_page)
        if not success:
            logging.info(f"{next_page}페이지 버튼이 없어 종료")
            break

        current_page = next_page
        time.sleep(1)  # 페이지 로딩 대기

    return all_data

###############################################################################
# 7. Google Sheets 연동
###############################################################################
def get_gspread_client_from_b64(service_account_json_b64):
    """
    Base64로 인코딩된 Google Service Account JSON을 디코딩하여 
    gspread.Client 인스턴스를 생성.
    """
    # 1) base64 디코딩
    json_bytes = base64.b64decode(service_account_json_b64)
    # 2) 문자열 변환
    json_str = json_bytes.decode('utf-8')
    # 3) JSON 파싱
    json_keyfile = json.loads(json_str)

    # 구글 스프레드시트 인증
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json_keyfile, scope)
    client = gspread.authorize(creds)
    return client

def update_jaego_sheet(jaego_sheet, item_cell_map, item_quantity_map):
    """
    재고 시트:
    1) 지정된 범위를 batch_clear로 초기화
    2) item_cell_map과 item_quantity_map을 사용해 batch_update로 일괄 기록
    """
    ranges_to_clear = [
        "G38:G45",
        "R38:R45",
        "AG38:AG45",
        "AR38:AR45",
        "BC38:BC45"
    ]
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
    """
    무궁 청라 시트:
    - E1에 적힌 날짜(YYYY-MM-DD) -> day(DD) 추출
    - U열(3~33)에서 동일 day 찾음 -> X열(24)에 revenue 입력
    """
    date_in_e1 = mugeung_sheet.acell('E1').value
    if not date_in_e1:
        logging.warning("[무궁 청라] E1에 날짜가 없습니다.")
        return

    day_str = date_in_e1.split("-")[-1]  # '27' 등
    try:
        day_str = str(int(day_str))  # '01' -> '1'
    except ValueError:
        logging.warning(f"[무궁 청라] 일자 추출 실패: {date_in_e1}")
        return

    date_cells = mugeung_sheet.range('U3:U33')
    found = False
    for cell in date_cells:
        if cell.value == day_str:
            row_num = cell.row
            mugeung_sheet.update_cell(row_num, 24, revenue)
            logging.info(f"[무궁 청라] E1={date_in_e1} -> day={day_str}, X{row_num}={revenue}")
            found = True
            break

    if not found:
        logging.warning(f"[무궁 청라] U열에서 일자 {day_str} 찾지 못함.")

###############################################################################
# 8. 메인 실행 흐름
###############################################################################
def main():
    setup_logging('script.log')

    # (1) 환경 변수 읽기
    coupang_id, coupang_pw, service_account_json_b64 = get_environment_variables()

    # (2) ChromeDriver
    driver = get_chrome_driver(use_profile=False)

    try:
        # (3) 쿠팡이츠 로그인
        login_coupang_eats(driver, user_id=coupang_id, password=coupang_pw)

        # (4) 오늘/조회
        click_today_and_search(driver)

        # (5) 매출액 추출
        today_revenue = get_today_revenue(driver)
        logging.info(f"[결과] 오늘 매출액: {today_revenue}")

        # (6) 주문 스크래핑 (무한 페이지)
        all_order_items = scrape_all_pages_by_buttons(driver)
        logging.info(f"[결과] 수집된 메뉴 아이템 총 {len(all_order_items)}개")

    except Exception as e:
        logging.error(f"에러 발생: {e}")
        traceback.print_exc()
        all_order_items = []
        today_revenue = 0

    finally:
        driver.quit()
        logging.info("WebDriver 종료")

    # (7) 구글 스프레드시트 처리
    try:
        # Base64 디코딩하여 gspread.Client 생성
        client = get_gspread_client_from_b64(service_account_json_b64)
        doc = client.open("청라 일일/월말 정산서")  # 문서 이름
        mugeung_sheet = doc.worksheet("무궁 청라")
        jaego_sheet = doc.worksheet("재고")

        # 매출액 업데이트
        update_revenue_by_day(mugeung_sheet, today_revenue)

        # 재고 업데이트
        item_cell_map = {
            '육회비빔밥': 'R43',
            '꼬리곰탕': 'G38',
            '빨간곰탕': 'G39',
            '꼬리덮밥': 'G40',
            '육전': 'R44',
            '육회': 'R42',
            '육사시미': 'R41',
            '꼬리수육': 'G41',
            '소꼬리찜': 'G42',
            '불꼬리찜': 'G43',
            '로제꼬리': 'G44',
            '꼬리구이': 'G45',
            '코카콜라 355ml': 'AG42',
            '스프라이트 355ml': 'AG43',
            '토닉워터 300ml': 'AG44',
            '제로콜라 355ml': 'AG41',
            '만월24 360ml': 'AR39',
            '문배술25 375ml': 'AR40',
            '배도가 로아 화이트 350ml': 'AR43',
            '황금보리 375ml': 'AR38',
            '사곡양조 왕율주 360ml': 'AR41',
            '왕주13 375ml': 'AR42',
            '청하 300ml': 'BC38',
            '참이슬 후레쉬 360ml': 'BC39',
            '처음처럼 360ml': 'BC40',
            '새로 360ml': 'BC42',
            '진로이즈백 360ml': 'BC41',
            '카스 500ml': 'BC43',
            '테라 500ml': 'BC44',
            '켈리 500ml': 'BC45',
            '소성주 750ml': 'AP45'
        }

        # 주문목록 -> {아이템명: 수량} 집계
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

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    main()

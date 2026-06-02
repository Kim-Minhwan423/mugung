import os
import sys
import re
import time
import datetime
import logging
import traceback
import base64
import json
import uuid
import tempfile

# -----------------------------
# Selenium
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

from selenium import webdriver
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
# 2. 환경 변수 불러오기
###############################################################################
def get_environment_variables():
    """
    필수 환경 변수:
      - CHENGLA_DDANGYO_ID (땡겨요 아이디)
      - CHENGLA_DDANGYO_PW (땡겨요 비밀번호)
      - SERVICE_ACCOUNT_JSON_BASE64 (Base64 인코딩된 Google Service Account JSON)
    """
    ddangyo_id = os.getenv("CHENGLA_DDANGYO_ID")
    ddangyo_pw = os.getenv("CHENGLA_DDANGYO_PW")
    service_account_json_b64 = os.getenv("SERVICE_ACCOUNT_JSON_BASE64")

    if not ddangyo_id or not ddangyo_pw:
        raise ValueError("CHENGLA_DDANGYO_ID 혹은 CHENGLA_DDANGYO_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    return ddangyo_id, ddangyo_pw, service_account_json_b64

###############################################################################
# 3. Chrome 드라이버 세팅 (고유 프로필 사용)
###############################################################################
def get_chrome_driver(use_profile=False):
    chrome_options = webdriver.ChromeOptions()
    # 필요 시 headless 모드 주석 해제
    chrome_options.add_argument("--headless")

    # User-Agent 변경
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/110.0.5481.77 Safari/537.36"
    )

    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1200,700")

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
# 4. 땡겨요 로그인 및 페이지 이동
###############################################################################
def login_ddangyo(driver, ddangyo_id, ddangyo_pw):
    driver.get("https://boss.ddangyo.com/")
    logging.info("땡겨요 사장님 사이트 로그인 페이지 접속 완료")

    time.sleep(1)

    id_selector = "#mf_ibx_mbrId"
    pw_selector = "#mf_sct_pwd"
    login_btn_selector = "#mf_btn_webLogin"

    try:
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, id_selector)))
        driver.find_element(By.CSS_SELECTOR, id_selector).send_keys(ddangyo_id)
        logging.info("아이디 입력")
        driver.find_element(By.CSS_SELECTOR, pw_selector).send_keys(ddangyo_pw)
        logging.info("비밀번호 입력")
        driver.find_element(By.CSS_SELECTOR, login_btn_selector).click()
        logging.info("로그인 버튼 클릭")
    except TimeoutException:
        logging.warning("로그인 페이지 로딩 Timeout")
    time.sleep(5)

def close_popup_if_exist(driver):
    popup_close_selector = "#mf_wfm_side_SMWCO050000P02SHOPP0000074_wframe_btn_view"
    try:
        close_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, popup_close_selector))
        )
        close_btn.click()
        logging.info("팝업 닫기 완료")
    except TimeoutException:
        logging.info("팝업이 나타나지 않음(혹은 이미 닫힘)")
    except Exception as e:
        logging.warning(f"팝업 닫기 중 예외 발생: {e}")
    time.sleep(2)

def go_order_history(driver):
    order_btn_selector = "#mf_wfm_side_gen_menuParent_3_gen_menuSub_1_btn_child"
    try:
        close_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, order_btn_selector))
        )
        close_btn.click()
        logging.info("주문내역 클릭 완료")
    except TimeoutException:
        logging.info("주문내역이 나타나지 않음(혹은 이미 닫힘)")
    except Exception as e:
        logging.warning(f"주문내역 클릭 중 예외 발생: {e}")
    time.sleep(2)

###############################################################################
# 5. 상품명 정규화 함수 (앞뒤 공백 제거 포함)
###############################################################################
def normalize_product_name(product_text):
    """
    1) 전각 괄호 -> 반각 괄호 치환
    2) " x 숫자" 부분 제거 -> 매핑 키와 동일하게 (ex: 소꼬리찜(2인분))
    """
    # 전각 괄호를 반각으로 교체
    product_text = product_text.replace("（", "(").replace("）", ")")
    # " x 숫자" 제거 (예: "육회비빔밥(1인분) x 1" -> "육회비빔밥(1인분)")
    product_text = re.sub(r"\s*x\s*\d+", "", product_text)
    return product_text.strip()

###############################################################################
# 6. 주문 날짜 파싱 헬퍼 함수
###############################################################################
def extract_number(text):
    return int(re.sub(r"[^\d]", "", text)) if text else 0

def parse_yyyymmdd(text):
    """
    예: 2025-02-06 14:31
    """
    match = re.search(r'(\d{4})[-.](\d{2})[-.](\d{2})', text)
    if not match:
        return None
    return datetime.date(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3))
    )

###############################################################################
# 7. 주문 상세 정보 추출 (오늘 날짜 기준)
###############################################################################
def get_todays_orders(driver):
    results = []
    today = datetime.date.today()

    for n in range(0, 101):
        link_id = f"mf_wfm_contents_gen_benefitsList_{n}_table_link_anchor"

        try:
            link = driver.find_element(By.ID, link_id)
        except NoSuchElementException:
            logging.info(f"N={n} 링크 없음 → 주문 리스트 종료")
            break

        logging.info(f"N={n} 주문 클릭")
        driver.execute_script("arguments[0].scrollIntoView(true);", link)
        link.click()
        time.sleep(2)

        # 날짜 확인
        try:
            date_elem = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located(
                    (By.ID, "mf_wfm_contents_SMWPU010000P02_wframe_grp_cmpt_dttm")
                )
            )
            order_date = parse_yyyymmdd(date_elem.text.strip())

            if order_date != today:
                logging.info(f"N={n} 주문 날짜 {order_date} → 오늘 아님")
                driver.back()
                time.sleep(1)
                continue

        except Exception as e:
            logging.warning(f"N={n} 날짜 확인 실패: {e}")
            driver.back()
            time.sleep(1)
            continue

        # 총 주문 금액
        try:
            amt_elem = driver.find_element(
                By.ID,
                "mf_wfm_contents_SMWPU010000P02_wframe_grp_tot_ord_amt"
            )
            total_amount = extract_number(amt_elem.text)
            logging.info(f"N={n} 총 주문금액: {total_amount}")
        except Exception:
            total_amount = 0

        # 메뉴 추출
        products = {}

        for i in range(0, 101):
            try:
                name_elem = driver.find_element(
                    By.ID,
                    f"mf_wfm_contents_SMWPU010000P02_wframe_gen_QryOrderDetailList_{i}_grp1_menu_nm"
                )
                qty_elem = driver.find_element(
                    By.ID,
                    f"mf_wfm_contents_SMWPU010000P02_wframe_gen_QryOrderDetailList_{i}_grp1_ord_qty"
                )

                name = normalize_product_name(name_elem.text.strip())
                qty = extract_number(qty_elem.text)

                products[name] = products.get(name, 0) + qty
                logging.info(f"메뉴: {name} x {qty}")

            except NoSuchElementException:
                logging.info(f"I={i} 메뉴 없음 → 메뉴 종료")
                break

        results.append({
            "order_index": n,
            "fee": total_amount,
            "products": products
        })

        driver.back()
        time.sleep(1)

    return results

###############################################################################
# 8. Google Sheets 업데이트 함수
###############################################################################
def update_google_sheets(total_order_amount, aggregated_products, service_account_json_b64):
    """
    - "청라 일일/월말 정산서" 스프레드시트의 "청라" 시트에서 U3:U33(날짜)와 Y3:Y33(주문 총액)을 업데이트
    - "재고" 시트의 지정 범위를 클리어한 후, 미리 정의한 매핑에 따라 각 품목의 수량을 업데이트
    """
    service_account_json = base64.b64decode(service_account_json_b64).decode("utf-8")
    service_account_info = json.loads(service_account_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scopes)
    gc = gspread.authorize(creds)
    sh = gc.open("청라 일일/월말 정산서")

    # 1) "청라" 시트: 총 주문금액 업데이트
    sheet_daily = sh.worksheet("청라")
    date_values = sheet_daily.get("U3:U33")
    today_day = str(datetime.datetime.today().day)
    row_index = None
    for i, row in enumerate(date_values, start=3):
        if row and row[0].strip() == today_day:
            row_index = i
            break

    if row_index:
        cell = f"Y{row_index}"
        sheet_daily.update_acell(cell, total_order_amount)
        logging.info(f"청라 시트 {cell}에 오늘 주문 총액 {total_order_amount} 업데이트")
    else:
        logging.warning("오늘 날짜에 해당하는 셀을 청라 시트에서 찾지 못함")

    # 2) "재고" 시트 업데이트
    sheet_inventory = sh.worksheet("재고")
    clear_ranges = ["H38:H45", "S38:S45", "AJ38:AJ45", "AU38:AU45", "BF38:BF45"]
    sheet_inventory.batch_clear(clear_ranges)

    update_mapping = {
        '백골뱅이숙회': 'H45',
        '얼큰소국밥': 'S38',
        '낙지비빔밥': 'AJ38',
        '낙지볶음': 'AJ40',
        '낙지파전': 'AJ39',
        '우삼겹김치전': 'S39',
        '두부김치제육': 'S40',
        '육회비빔밥': 'H42',
        '숙주갈비탕': 'H38',
        '갈비찜덮밥': 'H39',
        '육전': 'S44',
        '육회': 'H43',
        '육사시미': 'H44',
        '갈비수육': 'H40',
        '소갈비찜': 'H41',
        '소불고기': 'S42',
        '코카콜라': 'AJ42',
        '스프라이트': 'AJ43',
        '토닉워터': 'AJ44',
        '제로콜라': 'AJ41',
        '만월': 'AU39',
        '문배술25': 'AU40',
        '로아 화이트': 'AU43',
        '황금보리': 'AU38',
        '왕율주': 'AU41',
        '왕주': 'AU42',
        '청하': 'BF38',
        '참이슬 후레쉬': 'BF39',
        '처음처럼': 'BF40',
        '새로': 'BF42',
        '진로이즈백': 'BF41',
        '카스': 'BF43',
        '테라': 'BF44',
        '켈리': 'BF45',
        '소성주막걸리': 'AU45'
    }
    
    # (디버깅) aggregated_products 내용 로그
    logging.info(f"[DEBUG] 최종 aggregated_products: {aggregated_products}")

    batch_updates = []
    for product, cell in update_mapping.items():
        qty = aggregated_products.get(product, 0)
        value = "" if qty == 0 else qty
        batch_updates.append({
            "range": cell,
            "values": [[value]]
        })

    if batch_updates:
        sheet_inventory.batch_update(batch_updates)
        logging.info("재고 시트 업데이트 완료")

        # 업데이트 후 셀 값 확인 (예: I42)
        debug_val = sheet_inventory.acell("I42").value
        logging.info(f"[DEBUG] I42 셀 값: {debug_val}")

###############################################################################
# 메인 실행
###############################################################################
def main():
    setup_logging("script.log")

    # 🔴 에러 대비 기본값
    total_order_amount = -1
    aggregated_products = {}

    ddangyo_id, ddangyo_pw, service_account_json_b64 = get_environment_variables()
    driver = get_chrome_driver(use_profile=False)

    try:
        login_ddangyo(driver, ddangyo_id, ddangyo_pw)
        close_popup_if_exist(driver)
        go_order_history(driver)

        orders_data = get_todays_orders(driver)

        # 정상 수집 시에만 덮어쓰기
        total_order_amount = sum(order["fee"] for order in orders_data)

        for order in orders_data:
            for product, qty in order["products"].items():
                aggregated_products[product] = aggregated_products.get(product, 0) + qty

        logging.info(f"[DEBUG] orders_data: {orders_data}")
        logging.info(f"[DEBUG] total_order_amount: {total_order_amount}")

    except Exception as e:
        logging.error(f"❌ 에러 발생 → 매출 -1 기록: {e}")
        traceback.print_exc()

    finally:
        # ✅ 성공/실패 무조건 기록
        update_google_sheets(
            total_order_amount,
            aggregated_products,
            service_account_json_b64
        )

        try:
            driver.quit()
        except Exception:
            pass

        logging.info("WebDriver 종료")

if __name__ == "__main__":
    main()

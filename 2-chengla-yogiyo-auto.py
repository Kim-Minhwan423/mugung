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
# 0. 공백 제거를 위한 함수
###############################################################################
def strip_whitespace(data):
    """
    입력 데이터가 문자열, 딕셔너리, 리스트인 경우
    재귀적으로 앞뒤 공백을 제거합니다.
    """
    if isinstance(data, str):
        return data.strip()
    elif isinstance(data, dict):
        return {k.strip(): strip_whitespace(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [strip_whitespace(element) for element in data]
    else:
        return data

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
    # 필요 시 headless 모드 주석 해제
    #chrome_options.add_argument("--headless")

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

def go_store_selector(driver):
    store_xpath = "//*[@id='root']/div/div[2]/div[2]/div[1]/div/div"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, store_xpath)))
        driver.find_element(By.XPATH, store_xpath).click()
        logging.info("스토어 셀렉터 버튼 클릭")
    except TimeoutException:
        logging.warning("스토어 셀렉터 버튼을 찾지 못함")
    time.sleep(3)

def go_chengla_selector(driver):
    chengla_xpath = "//*[@id='root']/div/div[2]/div[2]/div[1]/div/div[2]/ul/li[2]/ul/li"
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, chengla_xpath)))
        driver.find_element(By.XPATH, chengla_xpath).click()
        logging.info("무궁 청라점 선택 완료")
    except TimeoutException:
        logging.warning("무궁 청라점 버튼을 찾지 못함")
    time.sleep(3)

def go_order_history(driver):
    order_btn_xpath = "//*[@id='root']/div/div[2]/div[2]/div[2]/div[1]/button[1]"
    
    # 최대 3번까지 재시도 (페이지 로딩 문제 해결)
    for attempt in range(3):
        try:
            logging.info(f"주문내역 버튼 클릭 시도 ({attempt+1}/3)")
            
            # 주문내역 버튼이 나타날 때까지 최대 15초 대기
            WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, order_btn_xpath)))
            driver.find_element(By.XPATH, order_btn_xpath).click()
            logging.info("주문내역 버튼 클릭 완료")
            time.sleep(3)  # 페이지 전환 대기
            return  # 성공하면 함수 종료

        except TimeoutException:
            logging.warning(f"주문내역 버튼을 찾지 못함 (시도 {attempt+1}/3)")

            if attempt < 2:
                logging.info("페이지를 새로고침 후 다시 시도합니다...")
                driver.refresh()  # 페이지 새로고침
                time.sleep(5)  # 새로고침 후 대기

    logging.error("3회 시도 후에도 주문내역 버튼을 찾지 못함 → 스크립트 종료")

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
def parse_yogiyo_order_date(date_text):
    """
    예) "02.06(목) 오후 04:31:59" -> '02.06' 부분만 파싱.
         (year는 현재 연도)
    """
    current_year = datetime.date.today().year
    match = re.search(r'(\d{2})\.(\d{2})', date_text)
    if not match:
        return None
    month = int(match.group(1))
    day   = int(match.group(2))
    try:
        return datetime.date(current_year, month, day)
    except ValueError:
        return None

###############################################################################
# 7. 주문 상세 정보 추출 (오늘 날짜 기준)
###############################################################################
def get_todays_orders(driver):
    """
    오늘 날짜의 주문만 가져와서,
    - 총 주문금액 (fee)
    - 판매 품목(제품명, 수량)
    을 리스트로 반환.
    """
    result_data = []
    today_date = datetime.date.today()

    for i in range(1, 11):  # 최대 10개의 주문 확인
        # (1) 주문 날짜 확인
        row_date_xpath = f"//*[@id='common-layout-wrapper-id']/div[1]/div/div/div[1]/div/div[2]/div/div/div/div[4]/table/tbody/tr[{i}]/td[1]/div"
        try:
            date_elem = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.XPATH, row_date_xpath))
            )
            raw_date_text = date_elem.text.strip()
            parsed_date = parse_yogiyo_order_date(raw_date_text)
            if not parsed_date:
                logging.info(f"{i}번째 행: '{raw_date_text}' → 날짜 파싱 실패 → 스킵")
                continue

            if parsed_date != today_date:
                logging.info(f"{i}번째 행: {raw_date_text} (파싱결과: {parsed_date}) 오늘 주문 아님 → 스킵")
                continue
        except TimeoutException:
            logging.warning(f"{i}번째 행 날짜를 찾지 못함 → 스킵")
            continue

        # (2) 상세보기 팝업 열기
        row_menu_xpath = f"//*[@id='common-layout-wrapper-id']/div[1]/div/div/div[1]/div/div[2]/div/div/div/div[4]/table/tbody/tr[{i}]/td[9]"
        try:
            row_elem = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, row_menu_xpath))
            )
            logging.info(f"--- {i}번째 행 (날짜: {parsed_date}) 클릭 시도 ---")
            driver.execute_script("arguments[0].scrollIntoView(true);", row_elem)
            row_elem.click()
            time.sleep(1)  # 팝업 열림 대기
        except TimeoutException:
            logging.warning(f"{i}번째 행 클릭 불가")
            continue
        except Exception as e:
            logging.error(f"{i}번째 행 클릭 중 오류: {e}")
            continue

        # (3) 총 주문금액
        fee_selector = (
            "#portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > "
            "div > div:nth-child(1) > div > li > "
            "div.OrderDetailPopup__OrderDeliveryFee-sc-cm3uu3-6.kCCvPa"
        )
        try:
            fee_elem = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, fee_selector))
            )
            fee_text = fee_elem.text.strip()
            fee_clean = re.sub(r"[^\d]", "", fee_text)  # 숫자만 추출
            fee_value = int(fee_clean) if fee_clean else 0
            logging.info(f"{i}번째 행 팝업: 추출된 총 주문금액 {fee_value}")
        except TimeoutException:
            logging.warning(f"{i}번째 행 팝업: 총 주문금액 요소를 찾지 못함")
            fee_value = 0
        except Exception as e:
            logging.error(f"{i}번째 행 팝업: 총 주문금액 추출 오류: {e}")
            fee_value = 0

        # (4) 품목 정보 추출
        products = {}
        j = 1
        while True:
            product_selector = (
                "#portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > "
                "div > div:nth-child(2) > div > div > "
                "div.OrderDetailPopup__OrderFeeListItem-sc-cm3uu3-10.gEOrSU > "
                f"div:nth-child({j}) > "
                "div.OrderDetailPopup__OrderFeeItemContent-sc-cm3uu3-14.jDwgnm > span:nth-child(1)"
            )
            try:
                product_elem = driver.find_element(By.CSS_SELECTOR, product_selector)
                product_text = product_elem.text.strip()

                # '배달요금' 같은 불필요 항목은 스킵
                if "배달요금" in product_text:
                    j += 1
                    continue

                # 1) 수량 파싱 (ex: "... x 2" -> 2)
                match = re.search(r"x\s*(\d+)", product_text)
                product_qty = int(match.group(1)) if match else 1

                # 2) 상품명 정규화 (ex: "소꼬리찜(2인분) x 1" -> "소꼬리찜(2인분)")
                cleaned_name = normalize_product_name(product_text)

                products[cleaned_name] = products.get(cleaned_name, 0) + product_qty
                logging.info(f"{i}번째 행 팝업: j={j}, 품명={cleaned_name}, 수량={product_qty}")
                j += 1
            except NoSuchElementException:
                logging.info(f"{i}번째 행 팝업: 더 이상 {j}번째 품목이 없음 → 품목 추출 완료")
                break
            except Exception as e:
                logging.error(f"{i}번째 행 팝업: j={j}번째 품목 추출 오류: {e}")
                break

        # (5) 팝업 닫기
        close_popup_selector = "#portal-root > div > div > div.FullScreenModal__Header-sc-7lyzl-1.eQqjUi > svg"
        try:
            close_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, close_popup_selector))
            )
            close_btn.click()
            logging.info(f"{i}번째 행 팝업 닫기 완료")
            time.sleep(1)
        except Exception as e:
            logging.error(f"{i}번째 행 팝업 닫기 오류: {e}")

        # result_data 저장
        result_data.append({
            "row_index": i,
            "fee": fee_value,
            "products": products
        })

    return result_data

###############################################################################
# 8. Google Sheets 업데이트 함수
###############################################################################
def update_google_sheets(total_order_amount, aggregated_products):
    """
    - "청라 일일/월말 정산서" 스프레드시트의 "무궁 청라" 시트에서 U3:U33(날짜)와 W3:W33(주문 총액)을 업데이트
    - "재고" 시트의 지정 범위를 클리어한 후, 미리 정의한 매핑에 따라 각 품목의 수량을 업데이트
    """
    yogiyo_id, yogiyo_pw, service_account_json_b64 = get_environment_variables()
    service_account_json = base64.b64decode(service_account_json_b64)
    service_account_info = json.loads(service_account_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scopes)
    gc = gspread.authorize(creds)

    sh = gc.open("청라 일일/월말 정산서")

    # 1) "무궁 청라" 시트: 총 주문금액 업데이트
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

    # 2) "재고" 시트 업데이트
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

        # 업데이트 후 셀 값 확인 (예: F42)
        debug_val = sheet_inventory.acell("F42").value
        logging.info(f"[DEBUG] F42 셀 값: {debug_val}")

###############################################################################
# 메인 실행
###############################################################################
def main():
    setup_logging("script.log")
    yogiyo_id, yogiyo_pw, _ = get_environment_variables()
    driver = get_chrome_driver(use_profile=False)

    try:
        # 1. 로그인 및 초기 팝업 처리
        login_yogiyo(driver, yogiyo_id, yogiyo_pw)
        close_popup_if_exist(driver)

        # 2. 매장(청라점) 선택 → 주문내역 페이지 진입
        go_store_selector(driver)
        go_chengla_selector(driver)
        close_popup_if_exist(driver)
        go_order_history(driver)

        # 3. 오늘의 주문내역 수집
        orders_data = get_todays_orders(driver)
        total_order_amount = sum(order["fee"] for order in orders_data)

        # 3-1. 전체 상품 집계
        aggregated_products = {}
        for order in orders_data:
            for product, qty in order["products"].items():
                aggregated_products[product] = aggregated_products.get(product, 0) + qty

        # (디버깅) 어떤 상품들이 몇 개 들어왔는지
        logging.info(f"[DEBUG] orders_data: {orders_data}")

        # 4. Google Sheets 업데이트
        update_google_sheets(total_order_amount, aggregated_products)

    except Exception as e:
        logging.error(f"에러 발생: {e}")
        traceback.print_exc()
    finally:
        driver.quit()
        logging.info("WebDriver 종료")

if __name__ == "__main__":
    main()

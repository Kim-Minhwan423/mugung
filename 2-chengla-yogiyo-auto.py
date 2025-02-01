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
# 1. 로깅 설정 (예시)
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
# 2. (예) 환경 변수 불러오기
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

    # 실제 운영 시, 아래처럼 값이 없으면 에러를 내주세요.
    if not yogiyo_id or not yogiyo_pw:
        raise ValueError("YOGIYO_ID 혹은 YOGIYO_PW 환경변수가 설정되지 않았습니다.")
    if not service_account_json_b64:
        raise ValueError("SERVICE_ACCOUNT_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    return yogiyo_id, yogiyo_pw, service_account_json_b64


###############################################################################
# 3. Chrome 드라이버 세팅 (고유 경로 프로필 사용 예시)
###############################################################################
def get_chrome_driver(use_profile=False):
    """
    ChromeDriver 설정
    """
    chrome_options = webdriver.ChromeOptions()
    #chrome_options.add_argument("--headless")  # 필요 시 활성화

    # User-Agent 변경
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/110.0.5481.77 Safari/537.36"
    )

    if use_profile:
        # 매 실행마다 임시폴더에 고유 폴더 생성
        unique_id = uuid.uuid4()
        user_data_dir = os.path.join(tempfile.gettempdir(), f"chrome_profile_{unique_id}")
        os.makedirs(user_data_dir, exist_ok=True)

        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        # 예: chrome_options.add_argument("--profile-directory=Default")
        logging.info(f"[use_profile=True] 고유 Chrome 프로필 경로: {user_data_dir}")

    # 일반 옵션들
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1029,657")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # 웹드라이버 티 안 나게
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
# 4. 요기요 로그인 → 팝업 닫기 → 셀프서비스 → 주문내역 진입
###############################################################################
def login_yogiyo(driver, yogiyo_id, yogiyo_pw):
    """
    1) https://ceo.yogiyo.co.kr/self-service-home/
    2) id, pw 입력
    3) 로그인 버튼
    """
    driver.get("https://ceo.yogiyo.co.kr/self-service-home/")
    logging.info("요기요 사장님 사이트 로그인 페이지 접속 완료")

    # 아이디 입력
    id_selector = "#root > div > div.LoginLayout__Container-sc-1dkvjmn-1.cFYxDO > div > div.Login__Container-sc-11eppm3-0.hruuNe > form > div:nth-child(1) > div > div.sc-fEOsli.iqThlJ > div.sc-bjUoiL.LLOzV > input"
    pw_selector = "#root > div > div.LoginLayout__Container-sc-1dkvjmn-1.cFYxDO > div > div.Login__Container-sc-11eppm3-0.hruuNe > form > div:nth-child(2) > div > div.sc-fEOsli.iqThlJ > div.sc-bjUoiL.LLOzV > input"
    login_btn_selector = "#root > div > div.LoginLayout__Container-sc-1dkvjmn-1.cFYxDO > div > div.Login__Container-sc-11eppm3-0.hruuNe > form > button"

    try:
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, id_selector)))
        driver.find_element(By.CSS_SELECTOR, id_selector).send_keys(yogiyo_id)
        logging.info("아이디 입력")

        driver.find_element(By.CSS_SELECTOR, pw_selector).send_keys(yogiyo_pw)
        logging.info("비밀번호 입력")

        # 로그인 버튼 클릭
        driver.find_element(By.CSS_SELECTOR, login_btn_selector).click()
        logging.info("로그인 버튼 클릭")
    except TimeoutException:
        logging.warning("로그인 페이지 로딩 Timeout")

    time.sleep(5)  # 로그인 처리 대기


def close_popup_if_exist(driver):
    """
    로그인 후 뜨는 팝업(#portal-root 등등) 닫기
    예시 CSS: #portal-root > div > ...
    """
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
        We출bDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, chengla_selector)))
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
# 5. 주문 금액, 품목 정보 추
###############################################################################
def extract_order_details(driver):
    """
    모달에서 주문 금액과 품목 정보를 추출하는 함수
    """
    try:
        # 주문 금액 추출 (예시 셀렉터)
        fee_selector = (
            "#portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > div > "
            "div:nth-child(1) > div > li > div.OrderDetailPopup__OrderDeliveryFee-sc-cm3uu3-6.kCCvPa"
        )
        order_fee = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, fee_selector))
        ).text

        # 품목 정보 추출 (동적 개수)
        # 공통 부모 셀렉터를 사용해 모든 품목 리스트를 가져옵니다.
        products_parent_selector = (
            "#portal-root > div > div > div.FullScreenModal__Container-sc-7lyzl-3.jJODWd > div > "
            "div:nth-child(2) > div > div > div.OrderDetailPopup__OrderFeeListItem-sc-cm3uu3-10.gEOrSU"
        )
        product_elements = driver.find_elements(By.CSS_SELECTOR, products_parent_selector)
        products = []
        for product in product_elements:
            try:
                # 예시: 첫번째 span 요소에 품목명이 있고, 필요시 주문갯수도 같이 가져온다면 추가 셀렉터로 추출합니다.
                product_name = product.find_element(
                    By.CSS_SELECTOR,
                    "div > div.OrderDetailPopup__OrderFeeItemContent-sc-cm3uu3-14.jDwgnm > span:nth-child(1)"
                ).text
                # 만약 주문갯수를 별도로 추출해야 한다면 아래와 같이 셀렉터 추가
                # product_qty = product.find_element(By.CSS_SELECTOR, "적절한_주문갯수_셀렉터").text
                products.append(product_name)  # 또는 (product_name, product_qty)
            except Exception as e:
                logging.warning(f"품목 정보 추출 중 오류: {e}")
        return order_fee, products

    except Exception as e:
        logging.error(f"주문 상세 정보 추출 오류: {e}")
        return None, []


def process_orders_on_page(driver, current_page):
    """
    현재 페이지 내의 모든 주문을 순회하며 상세 정보를 추출하는 함수
    """
    # 주문 목록 셀렉터 (페이지마다 최대 10건이 있음)
    orders_selector = (
        "#common-layout-wrapper-id > div.CommonLayout__Contents-sc-f8yrrc-1.fWTDpk > div > div > "
        "div.CardListLayout__CardListContainer-sc-26whdp-0.jofZaF.CardListLayout__StyledCardListLayout-sc-26whdp-1.lgKFYo > "
        "div > div.TitleContentCard__CardContentLayout-sc-1so7oge-0.fwXwFk > div > div > div > "
        "div.Table__Container-sc-s3p2z0-0.efwKvR > table > tbody > tr"
    )
    try:
        # 모든 주문 행들을 가져옵니다.
        orders = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, orders_selector))
        )
    except TimeoutException:
        logging.warning("주문 목록을 찾지 못함")
        return

    logging.info(f"페이지 {current_page}에 {len(orders)}건의 주문 발견")

    # 각 주문을 순차적으로 처리합니다.
    for idx, order in enumerate(orders, start=1):
        try:
            # 주문 클릭 시 동적 요소가 변경되므로, 주문 목록을 재조회하거나, 해당 요소가 클릭 가능하도록 보장해야 합니다.
            driver.execute_script("arguments[0].scrollIntoView(true);", order)
            order.click()
            logging.info(f"페이지 {current_page} 주문 {idx} 클릭")
            time.sleep(2)  # 모달 열림 대기

            # 모달에서 주문 상세 정보 추출
            fee, products = extract_order_details(driver)
            if fee:
                logging.info(f"페이지 {current_page} 주문 {idx}: 주문금액={fee}, 품목={products}")
            else:
                logging.warning(f"페이지 {current_page} 주문 {idx}: 상세 정보 추출 실패")

            # 모달 닫기 (닫기 버튼 셀렉터)
            close_modal_selector = "#portal-root > div > div > div.FullScreenModal__Header-sc-7lyzl-1.eQqjUi > svg"
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, close_modal_selector))
            ).click()
            logging.info(f"페이지 {current_page} 주문 {idx} 모달 닫기")
            time.sleep(1)  # 모달 닫힘 대기

        except Exception as e:
            logging.error(f"페이지 {current_page} 주문 {idx} 처리 중 오류: {e}")
            continue


def go_to_next_page(driver, current_page):
    """
    페이징 버튼을 이용해 다음 페이지로 이동하는 함수  
    (예시에서는 li 태그의 텍스트가 페이지 번호와 일치한다고 가정)
    """
    pagination_selector = (
        "#common-layout-wrapper-id > div.CommonLayout__Contents-sc-f8yrrc-1.fWTDpk > div > div > "
        "div.CardListLayout__CardListContainer-sc-26whdp-0.jofZaF.CardListLayout__StyledCardListLayout-sc-26whdp-1.lgKFYo > "
        "div > div.TitleContentCard__CardContentLayout-sc-1so7oge-0.fwXwFk > div > div > div > "
        "div.Pagination__Container-sc-iw43f5-3.jMWkBM > ul > li"
    )
    try:
        pages = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, pagination_selector))
        )
        next_page = None
        for page in pages:
            # 페이지 번호가 현재 페이지보다 1 큰 버튼을 찾습니다.
            if page.text.strip() == str(current_page + 1):
                next_page = page
                break
        if next_page:
            driver.execute_script("arguments[0].scrollIntoView(true);", next_page)
            next_page.click()
            logging.info(f"페이지 {current_page + 1}로 이동")
            time.sleep(3)  # 새 페이지 로딩 대기
            return True
        else:
            logging.info("더 이상의 페이지가 없음")
            return False
    except Exception as e:
        logging.error(f"페이지 이동 중 오류: {e}")
        return False


def process_all_order_pages(driver):
    """
    전체 주문 내역 페이지를 순회하며 각 주문의 정보를 추출하는 함수
    """
    current_page = 1
    while True:
        process_orders_on_page(driver, current_page)
        if not go_to_next_page(driver, current_page):
            break
        current_page += 1

###############################################################################
# 메인 실행 흐름 예시
###############################################################################
def main():
    setup_logging("script.log")

    # 환경 변수(아이디/비번) 가져오기
    yogiyo_id, yogiyo_pw, service_account_json_b64 = get_environment_variables()

    # use_profile=True 로 하면 고유 경로 프로필을 생성해 사용
    driver = get_chrome_driver(use_profile=True)

    try:
        # 1) 로그인
        login_yogiyo(driver, yogiyo_id, yogiyo_pw)

        # 2) 팝업 닫기
        close_popup_if_exist(driver)

        # 3) 청라점 진입
        go_store_selector(driver)
        go_chengla_selector(driver)
        
        # 4) 주문내역 진입
        go_order_history(driver)

        # 5) 주문금액, 품목명과 주문갯수 확인
        extract_order_details(driver)


    except Exception as e:
        logging.error(f"에러 발생: {e}")
        traceback.print_exc()
    finally:
        driver.quit()
        logging.info("WebDriver 종료")


if __name__ == "__main__":
    main()

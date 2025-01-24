import os
import re
import datetime
import logging
import traceback
import sys
import time  # 3초 대기를 위해 추가
import uuid  # 고유 User Data Directory 생성용

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

import gspread
from google.oauth2.service_account import Credentials
from gspread_formatting import CellFormat, NumberFormat, format_cell_range

# 1. CHENGLA_BAEMIN_ID, CHENGLA_BAEMIN_PW 환경 변수로부터 읽기
BAEMIN_USERNAME = os.getenv("CHENGLA_BAEMIN_ID")
BAEMIN_PASSWORD = os.getenv("CHENGLA_BAEMIN_PW")

# Google Service Account JSON 경로 (GitHub Actions 환경에서는 /tmp/keyfile.json 활용)
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/keyfile.json")

# 2. 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_formatter = logging.Formatter('%(message)s')
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)

file_handler = logging.FileHandler("script.log", encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)


# 3. Google Sheets API 인증 설정
def authorize_google_sheets(json_path):
    try:
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(json_path, scopes=scopes)
        client = gspread.authorize(creds)
        logging.info("Google Sheets API 인증에 성공했습니다.")
        return client
    except Exception as e:
        logging.error("Google Sheets API 인증에 실패했습니다.")
        logging.error(f"{str(e)}")
        raise


# 4. Selenium WebDriver 초기화
def initialize_webdriver(user_agent):
    try:
        options = webdriver.ChromeOptions()

        # (1) 유니크한 프로필 폴더 지정 → session not created 충돌 방지
        unique_dir = f"/tmp/chrome-user-data-{uuid.uuid4()}"
        options.add_argument(f"--user-data-dir={unique_dir}")

        # (2) 헤드리스 모드 사용 (원한다면 주석 해제)
        options.add_argument("--headless=new")

        # (3) 서버 환경 안정성 옵션
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        # (4) 기타 옵션: User-Agent 등
        options.add_argument(f"user-agent={user_agent}")
        options.add_argument("--window-size=1920x1080")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        logging.info("WebDriver가 성공적으로 초기화되었습니다.")
        return driver
    except WebDriverException as e:
        logging.error("WebDriver 초기화에 실패했습니다.")
        logging.error(f"{str(e)}")
        raise


# 5. 로그인 처리
def login(driver, wait, username, password):
    try:
        driver.get("https://self.baemin.com/")
        logging.info("배민 사이트에 접속 중...")

        # 로그인 페이지 로드 대기
        username_selector = "#root > div.style__LoginWrap-sc-145yrm0-0.hKiYRl > div > div > form > div:nth-child(1) > span > input[type=text]"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, username_selector)))

        # 사용자명 입력
        username_input = driver.find_element(By.CSS_SELECTOR, username_selector)
        username_input.clear()
        username_input.send_keys(username)
        logging.info("사용자명을 입력했습니다.")

        # 비밀번호 입력
        password_selector = "#root > div.style__LoginWrap-sc-145yrm0-0.hKiYRl > div > div > form > div.Input__InputWrap-sc-tapcpf-1.kjWnKT.mt-half-3 > span > input[type=password]"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, password_selector)))
        password_input = driver.find_element(By.CSS_SELECTOR, password_selector)
        password_input.clear()
        password_input.send_keys(password)
        logging.info("비밀번호를 입력했습니다.")

        # 로그인 버튼 클릭
        login_button_selector = "#root > div.style__LoginWrap-sc-145yrm0-0.hKiYRl > div > div > form > button"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, login_button_selector)))
        login_button = driver.find_element(By.CSS_SELECTOR, login_button_selector)
        login_button.click()
        logging.info("로그인 버튼을 클릭했습니다.")

        # 로그인 완료 대기
        menu_button_selector = "#root > div > div.Container_c_9rpk_1utdzds5.MobileHeader-module__mihN > div > div > div:nth-child(1)"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, menu_button_selector)))
        logging.info("로그인에 성공했습니다.")

    except TimeoutException:
        logging.error("로그인 페이지 로드 또는 로그인에 실패했습니다.")
        raise
    except Exception as e:
        logging.error("로그인 처리 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        raise


# 6. 팝업 닫기
def close_popup(driver, wait):
    popup_close_selector = "body > div.bsds-portal > div > section > footer > div > button"
    try:
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, popup_close_selector)))
        popup_close_button = driver.find_element(By.CSS_SELECTOR, popup_close_selector)
        popup_close_button.click()
        logging.info("팝업을 성공적으로 닫았습니다.")
    except TimeoutException:
        logging.warning("닫을 수 있는 팝업이 없거나 로드되지 않았습니다.")
    except Exception as e:
        logging.error("팝업을 닫는 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        raise


# 7. 메뉴 열기 및 주문내역으로 이동
def navigate_to_order_history(driver, wait):
    try:
        # 메뉴 버튼 클릭
        menu_button_selector = "#root > div > div.Container_c_9rpk_1utdzds5.MobileHeader-module__mihN > div > div > div:nth-child(1)"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector)))
        menu_button = driver.find_element(By.CSS_SELECTOR, menu_button_selector)
        menu_button.click()
        logging.info("메뉴 버튼을 클릭하여 메뉴창을 열었습니다.")

        # '주문내역' 클릭
        order_history_selector = "#root > div > div.frame-container.lnb-open > div.frame-aside > nav > div.MenuList-module__lZzf.LNB-module__foKc > ul:nth-child(10) > a:nth-child(1) > button"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, order_history_selector)))
        order_history_button = driver.find_element(By.CSS_SELECTOR, order_history_selector)
        order_history_button.click()
        logging.info("'주문내역' 버튼을 클릭했습니다.")

        # 주문내역 페이지 로드 대기
        date_filter_button_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.FilterContainer-module___Rxt > button.FilterContainer-module__vSPY.FilterContainer-module__vOLM"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, date_filter_button_selector)))
        logging.info("주문내역 페이지가 로드되었습니다.")

    except TimeoutException:
        logging.error("주문내역 페이지로 이동하는 데 실패했습니다.")
        raise
    except Exception as e:
        logging.error("주문내역 페이지로 이동 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        raise


# 8. 날짜 필터 설정
def set_date_filter(driver, wait):
    try:
        # 날짜 필터 버튼 클릭
        date_filter_button_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.FilterContainer-module___Rxt > button.FilterContainer-module__vSPY.FilterContainer-module__vOLM"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, date_filter_button_selector)))
        date_filter_button = driver.find_element(By.CSS_SELECTOR, date_filter_button_selector)
        date_filter_button.click()
        logging.info("날짜 필터 버튼을 클릭했습니다.")

        # '일・주' 라디오 버튼 선택
        daily_filter_xpath = "//label[contains(., '일・주')]/preceding-sibling::input[@type='radio']"
        wait.until(EC.element_to_be_clickable((By.XPATH, daily_filter_xpath)))
        daily_filter = driver.find_element(By.XPATH, daily_filter_xpath)
        daily_filter.click()
        logging.info("'일・주' 필터를 선택했습니다.")

        # '적용' 버튼 클릭
        apply_button_xpath = "//button[contains(., '적용')]"
        wait.until(EC.element_to_be_clickable((By.XPATH, apply_button_xpath)))
        apply_button = driver.find_element(By.XPATH, apply_button_xpath)
        apply_button.click()
        logging.info("'적용' 버튼을 클릭했습니다.")

        # 3초간 대기
        time.sleep(3)
        logging.info("3초간 대기했습니다.")

        # 필터 적용 후 데이터 로딩 대기
        summary_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.TotalSummary-module__sVL1 > div:nth-child(2) > span.TotalSummary-module__SysK > b"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, summary_selector)))
        logging.info("필터가 적용되고 데이터가 로드되었습니다.")

    except TimeoutException:
        logging.error("날짜 필터 설정에 실패했습니다.")
        raise
    except Exception as e:
        logging.error("날짜 필터 설정 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        raise


# 9. 주문 요약 데이터 추출
def extract_order_summary(driver, wait):
    try:
        summary_selector = "#root > div > div.frame-container > div.frame-wrap > div.frame-body > div.OrderHistoryPage-module__R0bB > div.TotalSummary-module__sVL1 > div:nth-child(2) > span.TotalSummary-module__SysK > b"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, summary_selector)))
        summary_element = driver.find_element(By.CSS_SELECTOR, summary_selector)
        summary_text = summary_element.text.strip()
        logging.info(f"주문 요약 데이터: {summary_text}")
        return summary_text
    except TimeoutException:
        logging.error("주문 요약 데이터를 추출하는 데 실패했습니다.")
        raise
    except NoSuchElementException:
        logging.error("주문 요약 데이터 요소를 찾을 수 없습니다.")
        raise
    except Exception as e:
        logging.error("주문 요약 데이터 추출 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        raise


# 10. Google Sheets에 주문 요약 데이터 기록
def update_order_summary_sheet(muGung_sheet, summary_text):
    try:
        # 현재 날짜의 일(day) 추출
        today = datetime.datetime.today()
        day = today.day
        logging.info(f"오늘 일자: {day}")

        # U3:U33 범위 읽기 (1~31일)
        date_cells = muGung_sheet.range('U3:U33')
        day_list = [cell.value for cell in date_cells]

        day_str = str(day)
        if day_str in day_list:
            index = day_list.index(day_str)  # 0-based index
            row_number = 3 + index
            target_column = 'V'
            target_cell = f"{target_column}{row_number}"

            summary_value = int(re.sub(r'[^\d]', '', summary_text))

            # (가장 중요한 부분) gspread는 위치 인자로만 update
            muGung_sheet.update(target_cell, [[summary_value]])
            logging.info(f"주문 요약 데이터를 {target_cell} 셀에 기록했습니다.")

            # V3:V33 셀 형식 지정 (천 단위 쉼표)
            format_cell_range(muGung_sheet, 'V3:V33', CellFormat(
                numberFormat=NumberFormat(
                    type='NUMBER',
                    pattern='#,##0'
                )
            ))
            logging.info("'무궁 청라' 시트의 V3:V33 셀 형식을 지정했습니다.")
        else:
            logging.warning(f"'무궁 청라' 시트에 오늘 일자({day})가 존재하지 않습니다.")

    except ValueError:
        logging.error(f"주문 요약 데이터 형식 오류: '{summary_text}'")
        raise
    except Exception as e:
        logging.error("Google Sheets에 데이터를 기록하는 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        raise


# 11. '재고' 시트의 특정 범위 데이터 삭제
def clear_inventory_sheet(inventory_sheet):
    try:
        ranges_to_clear = ['E38:E45', 'P38:P45', 'AD38:AD45', 'AP38:AP45', 'BA38:BA45']
        inventory_sheet.batch_clear(ranges_to_clear)
        logging.info("'재고' 시트의 지정된 범위를 삭제했습니다.")
    except Exception as e:
        logging.error("'재고' 시트의 데이터를 삭제하는 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        raise


# 12. 판매 수량 추출 및 '재고' 시트에 기록
def extract_and_update_sales_data(driver, wait, inventory_sheet, item_to_cell):
    try:
        logging.info("웹사이트에서 품목별 판매 수량 추출을 시작합니다.")
        sales_data = {}

        while True:
            # 현재 페이지의 모든 주문 처리
            for order_num in range(1, 20, 2):  # 1,3,5,...19
                if order_num == 1:
                    # 첫 번째 주문은 이미 열려 있음
                    order_details_tr_num = 2
                    logging.info("첫 번째 주문을 처리합니다.")
                else:
                    order_button_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_num}]/td/div/div'
                    try:
                        order_button = driver.find_element(By.XPATH, order_button_xpath)
                        order_button.click()
                        logging.info(f"tr[{order_num}] 버튼을 클릭했습니다.")

                        order_details_tr_num = order_num + 1
                        order_details_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_details_tr_num}]'
                        wait.until(EC.presence_of_element_located((By.XPATH, order_details_xpath)))
                        logging.info(f"tr[{order_details_tr_num}] 주문 상세가 로드되었습니다.")
                    except NoSuchElementException:
                        logging.info(f"tr[{order_num}]에 해당하는 버튼이 없습니다. 다음 주문으로 이동합니다.")
                        continue
                    except TimeoutException:
                        logging.error(f"tr[{order_num + 1}] 주문 상세 로드 실패.")
                        continue
                    except Exception as e:
                        logging.error(f"tr[{order_num}] 처리 중 오류 발생: {e}")
                        traceback.print_exc()
                        continue

                # 각 품목 추출
                for j in range(1, 100, 3):  # j=1,4,7,... 최대 99
                    item_name_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_details_tr_num}]/td/div/div/section[1]/div[3]/div[{j}]/span[1]/div/span[1]'
                    item_qty_xpath = f'//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[4]/div/table/tbody/tr[{order_details_tr_num}]/td/div/div/section[1]/div[3]/div[{j}]/span[1]/div/span[2]'

                    try:
                        item_name_element = driver.find_element(By.XPATH, item_name_xpath)
                        item_name = item_name_element.text.strip()

                        item_qty_element = driver.find_element(By.XPATH, item_qty_xpath)
                        item_qty_text = item_qty_element.text.strip()

                        match = re.search(r'\d+', item_qty_text.replace(',', ''))
                        if match:
                            sales_qty = int(match.group())
                        else:
                            logging.warning(f"수량을 추출할 수 없습니다: '{item_qty_text}'")
                            continue

                        if item_name in item_to_cell:
                            cell = item_to_cell[item_name]
                            if cell in sales_data:
                                sales_data[cell] += sales_qty
                            else:
                                sales_data[cell] = sales_qty
                            logging.info(f"품목: {item_name}, 판매 수량: {sales_qty}, 셀: {cell}")
                        else:
                            logging.warning(f"매핑되지 않은 품목: {item_name}, 판매 수량: {sales_qty}")

                    except NoSuchElementException:
                        logging.info(f"tr[{order_details_tr_num}]의 j={j} 품목/수량 요소가 없습니다. 다음 품목으로 이동.")
                        break
                    except Exception as e:
                        logging.error(f"tr[{order_details_tr_num}], j={j} 처리 중 오류: {e}")
                        traceback.print_exc()
                        break

            # 다음 페이지 버튼
            try:
                next_page_button_xpath = '//*[@id="root"]/div/div[3]/div[2]/div[1]/div[3]/div[5]/div/div[2]/span/button'
                next_page_button = driver.find_element(By.XPATH, next_page_button_xpath)
                if 'disabled' in next_page_button.get_attribute('class'):
                    logging.info("다음 페이지 없음. 종료.")
                    break
                next_page_button.click()
                logging.info("다음 페이지로 이동했습니다.")
                time.sleep(2)
            except NoSuchElementException:
                logging.info("다음 페이지 버튼 없음. 종료.")
                break
            except Exception as e:
                logging.error(f"다음 페이지로 이동 중 오류: {e}")
                traceback.print_exc()
                break

        # 모든 페이지 처리 후, batch_update
        if sales_data:
            batch = []
            for cell_address, qty in sales_data.items():
                batch.append({
                    'range': cell_address,
                    'values': [[qty]]
                })
                logging.info(f"배치 업데이트 준비: {cell_address} = {qty}")

            try:
                inventory_sheet.batch_update(batch)
                logging.info("'재고' 시트 판매 수량 배치 업데이트 완료.")
            except Exception as e:
                logging.error(f"'재고' 시트 업데이트 중 오류: {e}")
        else:
            logging.info("판매 데이터가 없습니다.")

    except Exception as e:
        logging.error("판매 수량 추출/기록 중 오류가 발생했습니다.")
        logging.error(f"{str(e)}")
        traceback.print_exc()
        raise


# 13. 메인 함수
def main():
    print("스크립트가 시작되었습니다.")

    # ------------------------------------------------
    # 1) 사용자 정의 User-Agent
    # ------------------------------------------------
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/120.0.0.0 Safari/537.36"
    )

    # ------------------------------------------------
    # 2) Google Sheets 인증
    # ------------------------------------------------
    client = authorize_google_sheets(GOOGLE_CREDENTIALS_PATH)
    spreadsheet = client.open("청라 일일/월말 정산서")
    muGung_sheet = spreadsheet.worksheet("무궁 청라")
    inventory_sheet = spreadsheet.worksheet("재고")

    # ------------------------------------------------
    # 3) WebDriver 초기화
    # ------------------------------------------------
    driver = initialize_webdriver(user_agent)
    wait = WebDriverWait(driver, 30)

    # ------------------------------------------------
    # 4) 배민 로그인 + 팝업 닫기 + 주문내역 페이지 이동
    # ------------------------------------------------
    try:
        if not BAEMIN_USERNAME or not BAEMIN_PASSWORD:
            raise ValueError("CHENGLA_BAEMIN_ID 혹은 CHENGLA_BAEMIN_PW 환경변수가 설정되지 않았습니다.")

        login(driver, wait, BAEMIN_USERNAME, BAEMIN_PASSWORD)
        close_popup(driver, wait)
        navigate_to_order_history(driver, wait)
        set_date_filter(driver, wait)

        # ------------------------------------------------
        # 5) 주문 요약 추출 + 구글 시트 기록
        # ------------------------------------------------
        summary_text = extract_order_summary(driver, wait)
        update_order_summary_sheet(muGung_sheet, summary_text)

        # ------------------------------------------------
        # 6) '재고' 시트 범위 삭제
        # ------------------------------------------------
        clear_inventory_sheet(inventory_sheet)

        # ------------------------------------------------
        # 7) 판매 수량 추출 + '재고' 시트에 기록
        # ------------------------------------------------
        item_to_cell = {
            '육회비빔밥(1인분)': 'P43',
            '꼬리곰탕(1인분)': 'E38',
            '빨간곰탕(1인분)': 'E39',
            '꼬리덮밥(1인분)': 'E40',
            '육전(200g)': 'P44',
            '육회(300g)': 'P42',
            '육사시미(250g)': 'P41',
            '꼬리수육(2인분)': 'E41',
            '소꼬리찜(2인분)': 'E42',
            '불꼬리찜(2인분)': 'E43',
            '로제꼬리(2인분)': 'E44',
            '꼬리구이(2인분)': 'E45',
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

        extract_and_update_sales_data(driver, wait, inventory_sheet, item_to_cell)

    except Exception as e:
        logging.error("프로세스 중 오류가 발생했습니다:")
        logging.error(f"{str(e)}")
        traceback.print_exc()
    finally:
        driver.quit()
        logging.info("WebDriver를 종료했습니다.")


# 14. 엔트리 포인트
if __name__ == "__main__":
    main()

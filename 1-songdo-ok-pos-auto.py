import os
import base64
import tempfile
import time
import gspread
import traceback
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timezone

def get_today_menu_cell():
    """
    오늘 요일에 따라 '오늘의메뉴'가 들어갈 재고 시트 셀 반환
    월=0, 화=1, 수=2, 목=3, 금=4
    """
    # 오늘 요일 구하기 (0=월, 1=화, ..., 6=일)
    weekday_idx = datetime.now().weekday()
    weekday_list = ["월", "화", "수", "목", "금", "토", "일"]
    weekday = weekday_list[weekday_idx]

    weekday_cell_map = {
        "월": "C38",
        "화": "C42",
        "수": "AB38",
        "목": "C39",
        "금": "N38"
    }

    return weekday_cell_map.get(weekday)  # 토/일이면 None

def main():
    try:
        # 로그 시작 시간
        current_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        current_local = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        print(f"[INFO] 스크립트 시작 시간 - UTC: {current_utc}, 로컬: {current_local}")


        # ================================
        # 1. Google Sheets API 인증 설정
        # ================================
        # User-Agent 설정
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/120.0.0.0 Safari/537.36"
        )

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        # GitHub Actions용: /tmp/keyfile.json 경로 (헤드리스 서버에서)
        decoded_json = base64.b64decode(
            os.environ["SERVICE_ACCOUNT_JSON_BASE64"]
        ).decode("utf-8")

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8"
        ) as temp:
            temp.write(decoded_json)
            json_path = temp.name
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
        client = gspread.authorize(creds)

        # 스프레드시트 열기 (예시)
        spreadsheet = client.open("송도 일일/월말 정산서")  # 스프레드시트 이름

        sheet_inventory = spreadsheet.worksheet("재고")    # '재고' 시트 선택
        sheet_report = spreadsheet.worksheet("송도")  # '송도' 시트 선택

        # ================================
        # 2. Chrome WebDriver 실행
        # ================================
        # --- 헤드리스 모드 + 한국어/ko-KR 설정 ---
        options = webdriver.ChromeOptions()

        # 1) Headless (GUI 없이 동작)
        #options.add_argument("--headless=new")  # 최신 headless 모드 사용

        # 2) 서버 환경 안정성 옵션
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        # 3) 언어 설정
        options.add_argument("--lang=ko-KR")
        options.add_experimental_option("prefs", {
            "intl.accept_languages": "ko,ko-KR"
        })

        # 4) 기타 설정
        options.add_argument("--window-size=1720,1080")
        options.add_argument(f"user-agent={user_agent}")

        # ChromeDriver 설치 및 WebDriver 초기화
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options
        )
        print("[INFO] Chrome WebDriver 초기화 완료.")

        # ================================================
        # 3. OKPOS 로그인 페이지 접속 및 로그인 진행
        # ================================================
        url = "https://okasp.okpos.co.kr/login/login_form.jsp"
        driver.get(url)
        print("[INFO] OKPOS 로그인 페이지에 접속했습니다.")

        # 프레임 전환
        driver.implicitly_wait(1)
        
        # ID 입력
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#user_id"))
        )
        id_input = driver.find_element(By.CSS_SELECTOR, "#user_id")
        id_input.click()
        id_input.clear()
        id_input.send_keys(os.getenv("SONGDO_OK_POS_ID"))
        print("[INFO] ID 입력 완료.")

        # PW 입력
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#user_pwd"))
        )
        pw_input = driver.find_element(By.CSS_SELECTOR, "#user_pwd")
        pw_input.click()
        pw_input.clear()
        pw_input.send_keys(os.getenv("SONGDO_OK_POS_PW"))
        print("[INFO] PW 입력 완료.")

        # 로그인 버튼 클릭
        login_button = driver.find_element(By.CSS_SELECTOR, "#loginForm > div:nth-child(4) > div:nth-child(5) > img")
        login_button.click()
        print("[INFO] 로그인 버튼 클릭 완료.")

        time.sleep(5)  # 로그인 후 화면 로딩 대기

        # ================================================
        # 4. 팝업 2개 완전 제거 (iframe 꼬임 방지)
        # ================================================
        driver.switch_to.default_content()

        popup_selectors = [
            "#divPopupCloseButton1 > button",
            "#divPopupCloseButton0 > button"
        ]

        for _ in range(3):  # 혹시 늦게 뜨는 경우 대비
            for selector in popup_selectors:
                try:
                    driver.switch_to.default_content()
                    btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    btn.click()
                    print(f"[INFO] 팝업 닫기 완료: {selector}")
                    time.sleep(1)
                except TimeoutException:
                    pass

        driver.switch_to.default_content()
        print("[INFO] 팝업 처리 완료, default_content 복귀")

        # ================================================
        # 5. 즐겨찾기 → 일자별 → 상품별 일매출분석
        # ================================================
        driver.switch_to.default_content()

        # 즐겨찾기 탭
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#divTopFrameHead > div:nth-child(2) > div:nth-child(2)"))
        )
        favorite_tab = driver.find_element(
            By.CSS_SELECTOR, "#divTopFrameHead > div:nth-child(2) > div:nth-child(2)"
        )
        favorite_tab.click()
        print("[INFO] 즐겨찾기 탭 클릭 완료.")
        time.sleep(1)

        # ===== 일자별 (MyMenuFrm iframe 안) =====
        driver.switch_to.default_content()

        WebDriverWait(driver, 10).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "MyMenuFrm"))
        )

        daily_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "sd3"))
        )
        daily_tab.click()
        print("[INFO] 일자별 클릭 완료.")
        time.sleep(2)

        driver.switch_to.default_content()
        WebDriverWait(driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "MainFrm"))
        )
        print("[INFO] MainFrm iframe 진입 완료.")

        product_tab = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "myTab1_tabTitle_5")))
        driver.execute_script("arguments[0].click();", product_tab)
        print("[INFO] 상품별 탭 클릭 완료.")
        time.sleep(1)
        
        # ================================================
        # 6. 조회 버튼
        # ================================================
        driver.switch_to.default_content()
        WebDriverWait(driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "MainFrm")))
        print("[INFO] 상품별 클릭 후 MainFrm 재진입 완료")

        WebDriverWait(driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it(
                (By.CSS_SELECTOR, "iframe[id^='myTab1PageFrm']")))
        print("[INFO] myTab1PageFrm iframe 진입 완료")

        driver.execute_script("fnSearch(1);")
        print("[INFO] 조회 fnSearch(1) 실행 완료")
        time.sleep(2)

        def process_rows_sequentially(driver, code_to_cell, special_prices, max_i=60):
            cell_qty_map = {}  # 셀별 누적 수량
            # =========================
            # 1️⃣ 일반 상품 처리 (special_prices에 있는 것만)
            # =========================
            for j in range(2, max_i + 1):
                try:
                    code_elem = driver.find_element(
                        By.CSS_SELECTOR,
                        f"#mySheet1-table > tbody > tr[3] > td > div > "
                        f"div.GMPageOne > table > tbody > tr:nth-child({j}) > td.HideCol0C5"
                    )
                    product_code = code_elem.text.strip()
                    if not product_code or product_code == "000047":
                        continue

                    if product_code not in special_prices or product_code not in code_to_cell:
                        continue

                    # 금액 기반 수량 계산
                    amount_elem = driver.find_element(
                        By.CSS_SELECTOR,
                        f"#mySheet1-table > tbody > tr[3]/td/div/div[1]/table/tbody/tr[{j}]/td.HideCol0C8"
                    )
                    amount_text = amount_elem.text.replace(",", "").strip()
                    amount = int(amount_text) if amount_text.isdigit() else 0

                    unit_price = special_prices[product_code]
                    qty = amount // unit_price if unit_price > 0 else 0

                    if qty > 0:
                        target_cell = code_to_cell[product_code]
                        cell_qty_map[target_cell] = cell_qty_map.get(target_cell, 0) + qty

                except Exception as e:
                    print(f"[WARN] 일반 상품 처리 j={j} 오류: {e}")
                    continue

            # =========================
            # 2️⃣ 오늘의 메뉴 처리 (000047)
            # =========================
            try:
                weekday_text = driver.find_element(
                    By.XPATH,
                    '//*[@id="mySheet1-table"]/tbody/tr[3]/td[1]/div/div[1]/table/tbody/tr[2]/td[3]'
                ).text.strip()  # "월", "화", "수", "목", "금"

                if weekday_text in ["월", "화", "수", "목", "금"]:
                    weekday_cell_map = {
                        "월": "C38",
                        "화": "C42",
                        "수": "AB38",
                        "목": "C39",
                        "금": "N38"
                    }
                    today_cell = weekday_cell_map[weekday_text]
                    cell_qty_map[today_cell] = cell_qty_map.get(today_cell, 0) + 1
                    print(f"[INFO] 오늘의 메뉴 1개 '{today_cell}' 셀에 기록")

            except Exception as e:
                print(f"[WARN] 오늘의 메뉴 처리 오류: {e}")

            # =========================
            # 3️⃣ batch_update용 변환
            # =========================
            return [{"range": cell, "values": [[qty]]} for cell, qty in cell_qty_map.items()]

        # ================================================
        # 7. 데이터 행 처리 및 스프레드시트 업데이트 ("재고" 시트)
        # ================================================
        # '재고' 시트용 셀 매핑 (실제 매핑에 맞게 수정 필요)
        code_to_cell_inventory = {
            "000001": "C38", "000002": "C39", "000003": "C42", "000004": "AB38",
            "000005": "N38", "000006": "N45", "000007": "C40",
            "000008": "C41", "000009": "N41", "000010": "C44",
            "000011": "C43", "000012": "AB40", "000013": "N40", "000014": "N44",
            "000015": "AB39", "000016": "N39", "000026": "AO39", "000027": "AO40",
            "000028": "AO43", "000029": "AO42", "000030": "AO41", "000031": "AO38",
            "000032": "AZ38", "000033": "AZ39", "000034": "AZ40", "000035": "AZ42",
            "000036": "AZ41", "000037": "AZ43", "000038": "AZ44", "000039": "AZ45", "000040": "AO45",
            "000041": "AB42", "000042": "AB41", "000043": "AB43", "000044": "AB44",
            "000045": "AB45", "000046": "C45"
        }

        special_prices = {
            "000041": 2000,  "000042": 2000,  "000044": 3000,  "000043": 2000,
            "000026": 28000, "000028": 22000, "000030": 18000, "000031": 18000,
            "000027": 28000
            # 필요하면 추가
        }

        # 데이터 행 처리 및 업데이트 리스트 생성
        update_cells_inventory = process_rows_sequentially(
            driver, 
            code_to_cell_inventory, 
            special_prices, 
            max_i=60  # i 값을 0~60으로 변경
        )

        # '재고' 시트의 특정 범위를 먼저 비웁니다.
        ranges_inventory_clear = [
            "C38", "C39", "C40", "C41", "C42", "C43", "C44", "C45",
            "N38", "N39", "N40", "N41", "N42", "N43", "N44", "N45",
            "AB38", "AB39", "AB40", "AB41", "AB42", "AB43", "AB44", "AB45",
            "AO38", "AO39", "AO40", "AO41", "AO42", "AO43", "AO44", "AO45",
            "AZ38", "AZ39", "AZ40", "AZ41", "AZ42", "AZ43", "AZ44", "AZ45"
        ]
        try:
            sheet_inventory.batch_clear(ranges_inventory_clear)
            print("[INFO] '재고' 시트 초기화 완료.")
        except Exception as e:
            print(f"[ERROR] '재고' 시트 초기화 실패: {e}")
            traceback.print_exc()

        # '재고' 시트 배치 업데이트 수행
        if update_cells_inventory:
            try:
                sheet_inventory.batch_update(update_cells_inventory)
                print("[INFO] '재고' 시트 배치 업데이트 완료.")
            except Exception as e:
                print(f"[ERROR] '재고' 시트 배치 업데이트 실패: {e}")
                traceback.print_exc()

        # ================================================
        # 8. 데이터 추출 및 스프레드시트 업데이트 ("송도" 시트)
        # ================================================
        driver.switch_to.default_content()
        WebDriverWait(driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "MainFrm"))
        )
        print("[INFO] MainFrm iframe 진입 완료.")

        # 일별종합 탭 클릭
        product_tab = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "myTab1_tabTitle_0"))
        )
        driver.execute_script("arguments[0].click();", product_tab)
        print("[INFO] 일별종합 탭 클릭 완료.")
        time.sleep(1)

        driver.switch_to.default_content()
        WebDriverWait(driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "MainFrm"))
        )
        print("[INFO] 상품별 클릭 후 MainFrm 재진입 완료")

        WebDriverWait(driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it(
                (By.CSS_SELECTOR, "iframe[id^='myTab1PageFrm']")
            )
        )
        print("[INFO] myTab1PageFrm iframe 진입 완료")

        # 조회 실행
        driver.execute_script("fnSearch();")
        print("[INFO] 조회 fnSearch() 실행 완료")
        time.sleep(2)

        # 안전하게 숫자 가져오는 함수
        
        def safe_get_int(xpath: str, label: str = "") -> int:
            try:
                el = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                text = el.text.strip().replace(",", "")
                if text.isdigit():
                    return int(text)
                else:
                    print(f"[WARN] {label} XPATH 읽었으나 숫자가 아님: '{text}'")
                    return -1  
            except TimeoutException:
                print(f"[ERROR] {label} XPATH 요소를 찾지 못함: {xpath}")
                return -1
            except Exception as e:
                print(f"[ERROR] {label} 읽는 중 예외 발생: {e}")
                return -1

        # XPATH 정의
        total_sales_xpath  = '//*[@id="mySheet1-table"]/tbody/tr[3]/td[2]/div/div[1]/table/tbody/tr[2]/td[20]'
        cash_sales_xpath   = '//*[@id="mySheet1-table"]/tbody/tr[3]/td[2]/div/div[1]/table/tbody/tr[2]/td[21]'
        cash_receipt_xpath = '//*[@id="mySheet1-table"]/tbody/tr[3]/td[2]/div/div[1]/table/tbody/tr[2]/td[22]'

        # 값 가져오기
        total_sales  = safe_get_int(total_sales_xpath)
        cash_sales   = safe_get_int(cash_sales_xpath)
        cash_receipt = safe_get_int(cash_receipt_xpath)

        # 카드 매출 계산
        card_sales = total_sales - (cash_sales + cash_receipt)
        net_cash_sales = cash_sales - cash_receipt  # 현금 = 총 현금 - 현금영수증

        # 전체 테이블 수
        total_tables_xpath = '//*[@id="mySheet1-table"]/tbody/tr[3]/td[2]/div/div[1]/table/tbody/tr[2]/td[7]'
        total_tables = safe_get_int(total_tables_xpath)

        # 구글 시트 업데이트 요청 만들기
        requests = []

        # 카드 매출
        requests.append({
            'updateCells': {
                'rows': [{'values': [{'userEnteredValue': {'numberValue': card_sales}}]}],
                'fields': 'userEnteredValue',
                'range': {'sheetId': sheet_report.id, 'startRowIndex': 2, 'endRowIndex': 3,
                          'startColumnIndex': 4, 'endColumnIndex': 5}  # E3
            }
        })

        # 현금 매출
        requests.append({
            'updateCells': {
                'rows': [{'values': [{'userEnteredValue': {'numberValue': net_cash_sales}}]}],
                'fields': 'userEnteredValue',
                'range': {'sheetId': sheet_report.id, 'startRowIndex': 4, 'endRowIndex': 5,
                          'startColumnIndex': 4, 'endColumnIndex': 5}  # E5
            }
        })

        # 현금영수증 매출
        requests.append({
            'updateCells': {
                'rows': [{'values': [{'userEnteredValue': {'numberValue': cash_receipt}}]}],
                'fields': 'userEnteredValue',
                'range': {'sheetId': sheet_report.id, 'startRowIndex': 5, 'endRowIndex': 6,
                          'startColumnIndex': 4, 'endColumnIndex': 5}  # E6
            }
        })

        # 전체 테이블 수
        requests.append({
            'updateCells': {
                'rows': [{'values': [{'userEnteredValue': {'numberValue': total_tables}}]}],
                'fields': 'userEnteredValue',
                'range': {'sheetId': sheet_report.id, 'startRowIndex': 30, 'endRowIndex': 31,
                          'startColumnIndex': 3, 'endColumnIndex': 4}  # D31
            }
        })

        # 전체 매출
        total_sales_int = total_sales  # total_sales 이미 int
        requests.append({
            'updateCells': {
                'rows': [{'values': [{'userEnteredValue': {'numberValue': total_sales_int}}]}],
                'fields': 'userEnteredValue',
                'range': {'sheetId': sheet_report.id, 'startRowIndex': 30, 'endRowIndex': 31,
                          'startColumnIndex': 4, 'endColumnIndex': 5}  # E31
            }
        })

        # 시트 초기화
        ranges_report_clear = ["E3", "E5", "E6", "D31", "E31"]
        try:
            sheet_report.batch_clear(ranges_report_clear)
            print("[INFO] '송도' 시트 초기화 완료.")
        except Exception as e:
            print(f"[ERROR] '송도' 시트 초기화 실패: {e}")
            traceback.print_exc()

        # 숫자 형식 설정
        number_format_requests = []
        for cell in ["E3", "E5", "E6", "E31"]:
            column_letter = ''.join(filter(str.isalpha, cell))
            row_number = int(''.join(filter(str.isdigit, cell)))
            start_col = ord(column_letter.upper()) - 65
            end_col = start_col + 1
            start_row = row_number - 1
            end_row = start_row + 1

            number_format_requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_report.id,
                              "startRowIndex": start_row, "endRowIndex": end_row,
                              "startColumnIndex": start_col, "endColumnIndex": end_col},
                    "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}},
                    "fields": "userEnteredFormat.numberFormat"
                }
            })

        # 모든 요청 합치기
        all_requests = requests + number_format_requests

        if all_requests:
            try:
                body = {"requests": all_requests}
                sheet_report.spreadsheet.batch_update(body)
                print("[INFO] '송도' 시트 배치 업데이트 및 형식 적용 완료.")
            except Exception as e:
                print(f"[ERROR] '송도' 시트 배치 업데이트 실패: {e}")
                traceback.print_exc()

    except Exception as e:
        print(f"[ERROR] 메인 함수 실행 중 예외 발생: {e}")
        traceback.print_exc()

        # ================================================
        # 비상 대처: 필요한 경우 추가적인 코드 실행
        # ================================================
        # 예: 로그 파일에 기록, 알림 보내기 등
        # 현재는 단순히 예외를 출력합니다.

    finally:
        # 브라우저를 자동으로 종료
        try:
            driver.quit()
            print("[INFO] 브라우저 종료 완료.")
        except Exception as e:
            print(f"[ERROR] 브라우저 종료 중 예외 발생: {e}")

if __name__ == "__main__":
    main()

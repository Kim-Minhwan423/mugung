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
        options.add_argument("--window-size=1920,1080")
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
        print("[INFO] EasyPOS 로그인 페이지에 접속했습니다.")

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

        time.sleep(30000)

        # 로그인 버튼 클릭
        login_button.click()
        print("[INFO] 로그인 버튼 클릭 완료.")

        # 🔑 로그인 후 mainframe 로딩 대기
        WebDriverWait(driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it(
                (By.NAME, "mainframe")
            )
        )
        print("[INFO] mainframe 프레임 전환 완료.")
        
        WebDriverWait(driver, 10).until(
            EC.frame_to_be_available_and_switch_to_it(
                (By.NAME, "childframe")
            )
        )
        print("[INFO] childframe 프레임 전환 완료.")

        time.sleep(3)  # 로그인 후 화면 로딩 대기

        # ================================================
        # 4. 팝업(비밀번호 변경 안내) 닫기
        # ================================================
        try:
            WebDriverWait(driver, 3).until(
                EC.visibility_of_element_located((By.ID, "mainframe_childframe_popupChangePasswd_titlebar_closebuttonAlignImageElement"))
            )
            close_btn = driver.find_element(
                By.ID, "mainframe_childframe_popupChangePasswd_titlebar_closebuttonAlignImageElement"
            )
            close_btn.click()
            print("[INFO] 비밀번호 변경 안내 팝업 닫기 완료.")
            time.sleep(1)
        except TimeoutException:
            # 팝업이 없으면 패스
            print("[INFO] 비밀번호 변경 안내 팝업이 존재하지 않습니다.")
            pass

        # ================================================
        # 5. 매출분석 → 상품분석 → 상품별 일매출분석
        # ================================================
        # 매출분석 탭
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divTop_img_TA_top_menu3 > div"))
        )
        sales_analysis_tab = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divTop_img_TA_top_menu3 > div"
        )
        sales_analysis_tab.click()
        print("[INFO] 매출분석 탭 클릭 완료.")
        time.sleep(1)

        # 상품분석 탭 클릭
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divLeftMenu_divLeftMainList_grdLeft_body_gridrow_1_cell_1_0_controltreeTextBoxElement"))
        )
        period_sales = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divLeftMenu_divLeftMainList_grdLeft_body_gridrow_1_cell_1_0_controltreeTextBoxElement"
        )
        period_sales.click()
        print("[INFO] 상품분석 탭 클릭 완료.")
        time.sleep(1)

        # 상품별 일매출분석 탭 클릭
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divLeftMenu_divLeftMainList_grdLeft_body_gridrow_6_cell_6_0_controltreeTextBoxElement"))
        )
        specific_period_item = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divLeftMenu_divLeftMainList_grdLeft_body_gridrow_6_cell_6_0_controltreeTextBoxElement"
        )
        specific_period_item.click()
        print("[INFO] 상품별 일매출분석 탭 클릭 완료.")
        time.sleep(1)

        # ================================================
        # 6. 당일 버튼 → 상품코드 표기 버튼 → 부가메뉴 포함 버튼 → 조회 버튼
        # ================================================
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_divSalesDate_btnNowDay"))
        )
        today_btn = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_divSalesDate_btnNowDay"
        )
        today_btn.click()
        print("[INFO] 당일 버튼 클릭 완료.")
        time.sleep(1)

        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_chkItemCd_chkimg"))
        )
        code_search_btn = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_chkItemCd_chkimg"
        )
        code_search_btn.click()
        print("[INFO] 상품코드 표기 버튼 클릭 완료.")
        time.sleep(1)

        # ▼ 드롭다운 열기
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_cboSrchFg_dropbutton"))
        )
        dropdown_btn = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_cboSrchFg_dropbutton"
        )
        dropdown_btn.click()
        print("[INFO] 부가메뉴 포함 드롭다운 열기 완료.")
        time.sleep(1)

        # ▼ 드롭다운에서 "부가메뉴포함" 항목 선택
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//div[contains(@id, "cboSrchFg_combopopup")]//div[contains(text(), "부가메뉴포함")]'))
        )
        menu_include_option = driver.find_element(
            By.XPATH, '//div[contains(@id, "cboSrchFg_combopopup")]//div[contains(text(), "부가메뉴포함")]'
        )
        menu_include_option.click()
        print("[INFO] '부가메뉴포함' 항목 클릭 완료.")
        time.sleep(1)

        # ▼ 조회 버튼 클릭
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divMainNavi_divCommonBtn_btnCommSearch"))
        )
        search_btn = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divMainNavi_divCommonBtn_btnCommSearch"
        )
        search_btn.click()
        print("[INFO] 조회 버튼 클릭 완료.")
        time.sleep(2)

        # ================================================
        # 7. 데이터 행 처리 및 스프레드시트 업데이트 ("재고" 시트)
        # ================================================
        # '재고' 시트용 셀 매핑 (실제 매핑에 맞게 수정 필요)
        code_to_cell_inventory = {
            "000001": "C42", "000002": "C38", "000003": "N40", "000004": "C39",
            "000005": "C40", "000006": "C41", "000009": "N38",
            "000010": "N41", "000011": "C44", "000012": "C43",
            "000018": "AB42", "000019": "AB43", "000020": "AB44", "000021": "AO40",
            "000022": "AO43", "000023": "AO38", "000024": "AO41", "000026": "AZ38",
            "000027": "AZ39", "000028": "AZ40", "000029": "AZ41", "000030": "AZ42",
            "000031": "AZ43", "000032": "AZ44", "000033": "AZ45", "000034": "C45",
            "000036": "N44", "000037": "N45", "000038": "AO42", "000039": "AO39", "000044": "AO45",
            "000047": "N39", "000048": "AB39", "000055": "AB41", "000056": "AB45",
            "000060": "AB40", "000061": "AB38", "000062": "N42"
        }

        special_prices = {
            "000018": 2000,  "000019": 2000,  "000020": 3000,  "000055": 2000,
            "000021": 28000, "000022": 22000, "000023": 18000, "000024": 18000,
            "000039": 28000
            # 필요하면 추가
        }

        # 데이터 행 처리 및 업데이트 리스트 생성
        update_cells_inventory = process_rows_sequentially(
            driver, 
            code_to_cell_inventory, 
            special_prices, 
            max_i=30  # i 값을 0~30으로 변경
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
        # 8. 영업속보 → 영업일보 → 영업일보 분석
        # ================================================
        # 영업속보 탭
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divTop_img_TA_top_menu2"))
        )
        sales_news_tab = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divTop_img_TA_top_menu2"
        )
        sales_news_tab.click()
        print("[INFO] 영업속보 탭 클릭 완료.")
        time.sleep(1)

        # 영업일보 탭 클릭
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divLeftMenu_divLeftMainList_grdLeft_body_gridrow_1_cell_1_0_controltreeTextBoxElement"))
        )
        daily_sales_tab = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divLeftMenu_divLeftMainList_grdLeft_body_gridrow_1_cell_1_0_controltreeTextBoxElement"
        )
        daily_sales_tab.click()
        print("[INFO] 영업일보 탭 클릭 완료.")
        time.sleep(1)

        # 영업일보 분석 탭 클릭
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divLeftMenu_divLeftMainList_grdLeft_body_gridrow_2_cell_2_0_controltreeTextBoxElement"))
        )
        sales_analysis_tab = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divLeftMenu_divLeftMainList_grdLeft_body_gridrow_2_cell_2_0_controltreeTextBoxElement"
        )
        sales_analysis_tab.click()
        print("[INFO] 영업일보 분석 탭 클릭 완료.")
        time.sleep(1)

        # ================================================
        # 9. 당일 버튼 → 조회 버튼
        # ================================================
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_divSalesDate3_btnNowDay"))
        )
        today_btn = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_divSalesDate3_btnNowDay"
        )
        today_btn.click()
        print("[INFO] 당일 버튼 클릭 완료.")
        time.sleep(1)

        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divMainNavi_divCommonBtn_btnCommSearch"))
        )
        search_btn = driver.find_element(
            By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divMainNavi_divCommonBtn_btnCommSearch"
        )
        search_btn.click()
        print("[INFO] 조회 버튼 클릭 완료.")
        time.sleep(2)

        # ================================================
        # 10. 데이터 추출 및 스프레드시트 업데이트 ("송도" 시트)
        # ================================================
        # '송도' 시트 업데이트를 위한 요청 리스트
        requests = []

        # 카드 매출
        try:
            card_sales = driver.find_element(
                By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_grdPaymentSale_body_gridrow_2_cell_2_2"
            ).text.strip().replace(",", "")
            card_sales_int = int(card_sales)
            requests.append({
                'updateCells': {
                    'rows': [{
                        'values': [{
                            'userEnteredValue': {
                                'numberValue': card_sales_int
                            }
                        }]
                    }],
                    'fields': 'userEnteredValue',
                    'range': {
                        'sheetId': sheet_report.id,
                        'startRowIndex': 2,  # E3: 0-based
                        'endRowIndex': 3,
                        'startColumnIndex': 4,  # E열: 0-based (E=4)
                        'endColumnIndex': 5
                    }
                }
            })
            print("[INFO] 카드 매출 데이터 수집 완료.")
        except Exception as e:
            print(f"[ERROR] 카드 매출 데이터 수집 실패: {e}")
            traceback.print_exc()

        # 현금 영수증 매출
        try:
            cash_receipt_sales = driver.find_element(
                By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_grdPaymentSale_body_gridrow_1_cell_1_2"
            ).text.strip().replace(",", "")
            cash_receipt_sales_int = int(cash_receipt_sales)
            requests.append({
                'updateCells': {
                    'rows': [{
                        'values': [{
                            'userEnteredValue': {
                                'numberValue': cash_receipt_sales_int
                            }
                        }]
                    }],
                    'fields': 'userEnteredValue',
                    'range': {
                        'sheetId': sheet_report.id,
                        'startRowIndex': 5,  # E6: 0-based
                        'endRowIndex': 6,
                        'startColumnIndex': 4,  # E열
                        'endColumnIndex': 5
                    }
                }
            })
            print("[INFO] 현금 영수증 매출 데이터 수집 완료.")
        except Exception as e:
            print(f"[ERROR] 현금 영수증 매출 데이터 수집 실패: {e}")
            traceback.print_exc()

        # 현금 매출 (총 현금 - 현금 영수증 매출)
        try:
            total_cash_sales = driver.find_element(
                By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_grdPaymentSale_body_gridrow_0_cell_0_2"
            ).text.strip().replace(",", "")
            total_cash_sales_value = int(total_cash_sales)
            net_cash_sales = total_cash_sales_value - cash_receipt_sales_int
            requests.append({
                'updateCells': {
                    'rows': [{
                        'values': [{
                            'userEnteredValue': {
                                'numberValue': net_cash_sales
                            }
                        }]
                    }],
                    'fields': 'userEnteredValue',
                    'range': {
                        'sheetId': sheet_report.id,
                        'startRowIndex': 4,  # E5: 0-based
                        'endRowIndex': 5,
                        'startColumnIndex': 4,  # E열
                        'endColumnIndex': 5
                    }
                }
            })
            print("[INFO] 현금 매출 데이터 수집 완료.")
        except Exception as e:
            print(f"[ERROR] 현금 매출 데이터 수집 실패: {e}")
            traceback.print_exc()

        # 전체 테이블 수
        try:
            total_tables = driver.find_element(
                By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_grdPaymentSale_summ_gridrow_-2_cell_-2_1"
            ).text.strip().replace(",", "")
            total_tables_int = int(total_tables)
            requests.append({
                'updateCells': {
                    'rows': [{
                        'values': [{
                            'userEnteredValue': {
                                'numberValue': total_tables_int
                            }
                        }]
                    }],
                    'fields': 'userEnteredValue',
                    'range': {
                        'sheetId': sheet_report.id,
                        'startRowIndex': 29,  # D30: 0-based
                        'endRowIndex': 30,
                        'startColumnIndex': 3,  # D열: 0-based (D=3)
                        'endColumnIndex': 4
                    }
                }
            })
            print("[INFO] 전체 테이블 수 데이터 수집 완료.")
        except Exception as e:
            print(f"[ERROR] 전체 테이블 수 데이터 수집 실패: {e}")
            traceback.print_exc()

        # 전체 매출
        try:
            total_sales = driver.find_element(
                By.CSS_SELECTOR, "#mainframe_childframe_form_divMain_divWork_grdPaymentSale_summ_gridrow_-2_cell_-2_2"
            ).text.strip().replace(",", "")
            total_sales_int = int(total_sales)
            requests.append({
                'updateCells': {
                    'rows': [{
                        'values': [{
                            'userEnteredValue': {
                                'numberValue': total_sales_int
                            }
                        }]
                    }],
                    'fields': 'userEnteredValue',
                    'range': {
                        'sheetId': sheet_report.id,
                        'startRowIndex': 29,  # E30: 0-based
                        'endRowIndex': 30,
                        'startColumnIndex': 4,  # E열
                        'endColumnIndex': 5
                    }
                }
            })
            print("[INFO] 전체 매출 데이터 수집 완료.")
        except Exception as e:
            print(f"[ERROR] 전체 매출 데이터 수집 실패: {e}")
            traceback.print_exc()

        # "송도" 시트의 특정 범위를 먼저 비웁니다.
        ranges_report_clear = ["E3", "E5", "E6", "D30", "E30"]
        try:
            sheet_report.batch_clear(ranges_report_clear)
            print("[INFO] '송도' 시트 초기화 완료.")
        except Exception as e:
            print(f"[ERROR] '송도' 시트 초기화 실패: {e}")
            traceback.print_exc()

        # 숫자 형식 설정을 위한 요청 추가
        number_format_requests = []
        for cell in ["E3", "E5", "E6", "E30"]:
            column_letter = ''.join(filter(str.isalpha, cell))
            row_number = int(''.join(filter(str.isdigit, cell)))
            start_col = ord(column_letter.upper()) - 65
            end_col = start_col + 1
            start_row = row_number - 1
            end_row = start_row + 1

            number_format_requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_report.id,
                        "startRowIndex": start_row,
                        "endRowIndex": end_row,
                        "startColumnIndex": start_col,
                        "endColumnIndex": end_col
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {
                                "type": "NUMBER",
                                "pattern": "#,##0"
                            }
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            })

        # 모든 요청을 하나의 리스트로 합칩니다.
        all_requests = requests + number_format_requests

        # "송도" 시트 배치 업데이트 수행
        if all_requests:
            try:
                body = {
                    "requests": all_requests
                }
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

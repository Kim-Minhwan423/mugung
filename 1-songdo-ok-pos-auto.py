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
from webdriver_manager.chrome import ChromeDriverManager
TIMEOUT = 10

# =====================================================
# 숫자 안전 추출
# =====================================================
def get_int(driver, xpath, default=0):
    try:
        txt = WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        ).text.replace(",", "").strip()
        return int(txt) if txt.isdigit() else default
    except:
        return default
# =====================================================
# OKPOS 공지 / 팝업 닫기
# =====================================================
# =====================================================
# OKPOS 모든 팝업 닫기 (안전 버전)
# =====================================================
# =====================================================
# OKPOS 팝업 + 배경 완전 제거
# =====================================================
def close_okpos_popup(driver):
    driver.switch_to.default_content()

    popup_buttons = [
        "#divPopupCloseButton0 > button",
        "#divPopupCloseButton1 > button"
    ]

    # 버튼은 있으면 무조건 누른다 (여러 번 시도)
    for _ in range(3):
        for sel in popup_buttons:
            try:
                btn = WebDriverWait(driver, TIMEOUT).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.3)
                print(f"[INFO] 팝업 닫기 클릭: {sel}")
            except:
                pass

    # ✅ 배경 오버레이가 사라질 때까지 대기
    try:
        WebDriverWait(driver, TIMEOUT).until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "[id^='divPopupBackground']")
            )
        )
        print("[INFO] 팝업 배경 제거 완료")
    except:
        print("[WARN] 팝업 배경 대기 타임아웃 (진행)")
# =====================================================
# OKPOS fnSearch 안전 실행 (MainFrm 내부 iframe 대응)
# =====================================================
def okpos_fn_search(driver, timeout=10):
    driver.switch_to.default_content()

    # 1️⃣ MainFrm 진입
    WebDriverWait(driver, TIMEOUT).until(
        EC.frame_to_be_available_and_switch_to_it("MainFrm")
    )

    # 2️⃣ MainFrm 내부 myTab1PageFrm* iframe 찾기
    inner_iframe = WebDriverWait(driver, TIMEOUT).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "iframe[id^='myTab1PageFrm']")
        )
    )

    driver.switch_to.frame(inner_iframe)

    # 3️⃣ fnSearch 실행
    driver.execute_script("fnSearch();")
    time.sleep(2)

    print("[INFO] fnSearch 실행 완료 (inner iframe)")
# =====================================================
# 일별종합 데이터 추출
# =====================================================
def extract_daily_summary(driver, sheet):
    data_map = {
        "현금": '//*[@id="mySheet1-table"]/tbody/tr[3]/td[2]/div/div[1]/table/tbody/tr[2]/td[21]',
        "현금영수증": '//*[@id="mySheet1-table"]/tbody/tr[3]/td[2]/div/div[1]/table/tbody/tr[2]/td[22]',
        "테이블수": '//*[@id="mySheet1-table"]/tbody/tr[3]/td[2]/div/div[1]/table/tbody/tr[2]/td[9]',
        "총매출": '//*[@id="mySheet1-table"]/tbody/tr[3]/td[2]/div/div[1]/table/tbody/tr[2]/td[4]'
    }
    
    total = values["총매출"]
    cash = values["현금"]
    cash_receipt = values["현금영수증"]

    card = total - cash - cash_receipt
    if card < 0:
        card = 0

    values = {}
    for k, xp in data_map.items():
        values[k] = get_int(driver, xp)

    sheet.batch_update([
        {"range": "E3", "values": [[card]]},          # 카드 (계산값)
        {"range": "E5", "values": [[cash]]},          # 현금
        {"range": "E6", "values": [[cash_receipt]]},  # 현금영수증
        {"range": "D31", "values": [[values["테이블수"]]]},
        {"range": "E31", "values": [[total]]},
    ])

    print("[INFO] 일별종합 데이터 업데이트 완료")


# =====================================================
# 재고 처리
# =====================================================
def process_inventory(driver, sheet_inventory):
    code_to_cell = {
        "000001": "C38", "000056": "C38",
        "000002": "C39", "000057": "C39",
        "000003": "C42", "000058": "C42",
        "000004": "AB38", "000059": "AB38",

        "000005": "N38", "000006": "N45", "000007": "C40",
        "000008": "C41", "000009": "N41", "000010": "C44",
        "000011": "C43", "000012": "AB40", "000013": "N40", "000014": "N44",
        "000015": "AB39", "000016": "N39",

        "000026": "AO39", "000027": "AO40", "000028": "AO43",
        "000029": "AO42", "000030": "AO41", "000031": "AO38",

        "000032": "AZ38", "000033": "AZ39", "000034": "AZ40",
        "000035": "AZ42", "000036": "AZ41", "000037": "AZ43",
        "000038": "AZ44", "000039": "AZ45", "000040": "AO45",

        "000041": "AB42", "000042": "AB41", "000043": "AB43",
        "000044": "AB44", "000045": "AB45", "000046": "C45"
    }


    special_prices = {
        "000041": 2000, "000042": 2000, "000043": 2000,
        "000044": 3000,
        "000026": 28000, "000027": 28000,
        "000028": 22000,
        "000030": 18000, "000031": 18000
    }

    # 재고 영역 초기화
    sheet_inventory.batch_clear(list(code_to_cell.values()))

    updates = []
    cell_qty_map = {}

    for row in range(2, 61):
        try:
            code = driver.find_element(
                By.XPATH,
                f'//*[@id="mySheet1-table"]/tbody/tr[3]/td/div/div[1]/table/tbody/tr[{row}]/td[6]'
            ).text.strip()

            if code not in code_to_cell:
                continue

            raw_value = get_int(
                driver,
                f'//*[@id="mySheet1-table"]/tbody/tr[3]/td/div/div[1]/table/tbody/tr[{row}]/td[8]'
            )

            if code in special_prices:
                qty = raw_value // special_prices[code] if raw_value else 0
            else:
                qty = raw_value

            if qty > 0:
                cell = code_to_cell[code]
                cell_qty_map[cell] = cell_qty_map.get(cell, 0) + qty

        except Exception:
            continue

    updates = [
        {"range": cell, "values": [[qty]]}
        for cell, qty in cell_qty_map.items()
    ]

    if updates:
        sheet_inventory.batch_update(updates)
    print("[INFO] 재고 시트 업데이트 완료")

# =====================================================
# 메인
# =====================================================
def main():
    driver = None
    try:
        decoded = base64.b64decode(os.environ["SERVICE_ACCOUNT_JSON_BASE64"]).decode()
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(decoded)
            json_path = f.name

        creds = ServiceAccountCredentials.from_json_keyfile_name(
            json_path,
            [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open("송도 일일/월말 정산서")

        sheet_report = spreadsheet.worksheet("송도")
        sheet_inventory = spreadsheet.worksheet("재고")

        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=1720,1080")

        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options
        )

        driver.get("https://okasp.okpos.co.kr/login/login_form.jsp")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "user_id")))
        driver.find_element(By.ID, "user_id").send_keys(os.getenv("SONGDO_OK_POS_ID"))
        driver.find_element(By.ID, "user_pwd").send_keys(os.getenv("SONGDO_OK_POS_PW"))
        driver.find_element(By.CSS_SELECTOR, "#loginForm > div:nth-child(4) > div:nth-child(5) > img").click()
        time.sleep(5)

        # ✅ 팝업 전부 닫기
        close_okpos_popup(driver)

        # 즐겨찾기 → 일별종합
        top_menu = WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#divTopFrameHead > div:nth-child(2) > div:nth-child(2)")
            )
        )
        driver.execute_script("arguments[0].click();", top_menu)
        time.sleep(1)
        driver.switch_to.default_content()
        WebDriverWait(driver, TIMEOUT).until(
            EC.frame_to_be_available_and_switch_to_it("MyMenuFrm")
        )
        driver.find_element(By.ID, "sd3").click()
        time.sleep(2)

        okpos_fn_search(driver)
        extract_daily_summary(driver, sheet_report)

        # 상품별 탭 클릭
        driver.switch_to.default_content()
        WebDriverWait(driver, TIMEOUT).until(
            EC.frame_to_be_available_and_switch_to_it("MainFrm")
        )

        driver.execute_script(
            "arguments[0].click();",
            WebDriverWait(driver, TIMEOUT).until(
                EC.presence_of_element_located((By.ID, "myTab1_tabTitle_5"))
            )
        )

        time.sleep(1)

        # ✅ 다시 공용 fnSearch 실행
        okpos_fn_search(driver)
        process_inventory(driver, sheet_inventory)

    except Exception:
        traceback.print_exc()

    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()

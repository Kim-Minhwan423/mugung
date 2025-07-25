import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# User-Agent 설정
user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    " AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/120.0.0.0 Safari/537.36"
)

# Google Sheets API 인증
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

json_path = "/tmp/keyfile.json"
creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
client = gspread.authorize(creds)

spreadsheet = client.open("송도 일일/월말 정산서")  # 🔄 문서명 변경됨
sheet = spreadsheet.worksheet("예약&마케팅")

# --- 헤드리스 모드 + 설정 조정 ---
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")  # 새로운 headless 모드
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--disable-software-rasterizer")
options.add_argument("--remote-debugging-port=9222")
options.add_argument("--lang=ko-KR")
options.add_argument("--window-size=1920,1080")
options.add_argument(f"user-agent={user_agent}")
options.page_load_strategy = 'eager'  # 페이지 로딩 전략 간소화

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)
driver.set_page_load_timeout(40)

keywords = [kw.strip() for kw in sheet.col_values(2)[82:200] if kw.strip()]
real_places = []

def robust_scroll():
    try:
        scroll_container = driver.find_element(By.XPATH, "//*[@id='_pcmap_list_scroll_container']")
    except NoSuchElementException:
        print("🚨 스크롤 컨테이너를 찾지 못했습니다.")
        return []

    previous_count = 0
    max_attempts = 50
    attempts = 0

    while attempts < max_attempts:
        places = scroll_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")
        current_count = len(places)

        if current_count == previous_count:
            break

        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", places[-1])
        except WebDriverException as e:
            print(f"🚨 스크롤 중 오류 발생: {e}")
            break

        previous_count = current_count
        attempts += 1
        time.sleep(1.5)

    return scroll_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")

def go_to_next_page(page_idx):
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.zRM9F > a"))
        )
        buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")

        if page_idx < len(buttons):
            driver.execute_script("arguments[0].click();", buttons[page_idx])
            time.sleep(3)
        else:
            print(f"🚨 page_idx={page_idx}가 버튼 범위 밖입니다.")
    except Exception as e:
        print(f"🚨 다음 페이지 이동 실패: {e}")

def get_places_from_page():
    place_elements = robust_scroll()

    for place in place_elements:
        try:
            name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text.strip()
            if not name:
                continue
            if "cZnHG" not in place.get_attribute("class"):
                if name not in real_places:
                    real_places.append(name)
        except Exception:
            continue

def wait_for_iframe(driver, xpath, timeout=40):
    for _ in range(timeout):
        try:
            iframe = driver.find_element(By.XPATH, xpath)
            return iframe
        except NoSuchElementException:
            time.sleep(1)
    return None


def get_place_rank(keyword, target_place="무궁 송도점"):
    real_places.clear()
    driver.get(f"https://map.naver.com/v5/search/{keyword}")

    # iframe 대기 (최대 40초)
    iframe = wait_for_iframe(driver, "//*[@id='searchIframe']", timeout=40)
    if not iframe:
        print(f"🚨 '{keyword}' 검색 실패: iframe 로드 시간 초과")
        return "로딩실패"

    try:
        driver.switch_to.default_content()
        driver.switch_to.frame(iframe)
    except Exception as e:
        print(f"🚨 iframe 전환 실패: {e}")
        return "로딩실패"

    try:
        # 페이지 버튼 수를 다시 가져올 때도 항상 최신 요소를 새로 조회
        WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.zRM9F > a"))
        )
        page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
        total_pages = len(page_buttons) if page_buttons else 1
    except Exception:
        total_pages = 1

    for page_num in range(1, min(total_pages, 5) + 1):
        get_places_from_page()
        if page_num < total_pages:
            go_to_next_page(page_num)

    if target_place in real_places:
        return real_places.index(target_place) + 1
    return None

# --- Batch Update ---
start_row = 83
column_rank = 5
update_data = []

for i, keyword in enumerate(keywords, start=start_row):
    try:
        rank = get_place_rank(keyword)
        if rank:
            print(f"✅ '{keyword}'의 순위는 {rank}")
            update_data.append([rank])
        elif rank == "로딩실패":
            update_data.append(["로딩실패"])
        else:
            print(f"🚨 '{keyword}'의 순위를 찾지 못했습니다.")
            update_data.append(["검색결과없음"])
    except Exception as e:
        print(f"🚨 '{keyword}' 처리 중 오류: {str(e)}")
        update_data.append([f"오류: {str(e)}"])

end_row = start_row + len(update_data) - 1
update_range = f"E{start_row}:E{end_row}"

try:
    sheet.update(range_name=update_range, values=update_data)
    print("✅ Google Sheets에 순위 업데이트 완료 (E열만)")
except Exception as e:
    print(f"🚨 배치 업데이트 중 오류 발생: {e}")

driver.quit()
print("✅ 모든 키워드 순위 업데이트 완료")

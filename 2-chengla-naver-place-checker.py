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

# GitHub Actions용: /tmp/keyfile.json 경로 (헤드리스 서버에서)
json_path = "/tmp/keyfile.json"  
creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
client = gspread.authorize(creds)

# 스프레드시트 열기 (예시)
spreadsheet = client.open("청라 일일/월말 정산서")
sheet = spreadsheet.worksheet("체험단&예약")

# --- 헤드리스 모드 + 한국어/ko-KR 설정 ---
options = webdriver.ChromeOptions()

# 1) Headless (GUI 없이 동작)
options.add_argument("--headless")

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

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

# 키워드 (예: B55 ~ B80)
keywords = sheet.col_values(2)[54:80]

# 광고 제외 플레이스 목록
real_places = []

def robust_scroll():
    """
    스크롤을 여러 번 시도해서, 최대한 많은 place 요소를 불러오는 함수.
    - 최대 30회
    - 스크롤 후 5초 대기
    """
    try:
        scroll_container = driver.find_element(By.XPATH, "//*[@id='_pcmap_list_scroll_container']")
    except NoSuchElementException:
        print("🚨 스크롤 컨테이너를 찾지 못했습니다.")
        return []

    previous_count = 0
    max_attempts = 30
    attempts = 0

    while attempts < max_attempts:
        places = scroll_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")
        current_count = len(places)

        if current_count == previous_count:
            # 더 이상 늘어나지 않으면 종료
            break

        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", places[-1])
        except WebDriverException as e:
            print(f"🚨 스크롤 중 오류 발생: {e}")
            break

        previous_count = current_count
        attempts += 1
        time.sleep(5)  # 스크롤 후 충분히 대기

    return scroll_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")

def go_to_next_page(page_idx):
    """
    page_idx에 해당하는 페이지 버튼 클릭 후, 5초 대기
    """
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.zRM9F > a"))
        )
        buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")

        if page_idx < len(buttons):
            driver.execute_script("arguments[0].click();", buttons[page_idx])
            time.sleep(5)  # 페이지 전환 후 충분히 대기
        else:
            print(f"🚨 page_idx={page_idx}가 버튼 범위 밖입니다.")
    except Exception as e:
        print(f"🚨 다음 페이지 이동 실패: {e}")

def get_places_from_page():
    """
    robust_scroll() 호출 후,
    광고 제외한 플레이스 이름을 real_places에 추가
    """
    place_elements = robust_scroll()

    for place in place_elements:
        try:
            name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text.strip()
            if not name:
                continue
            # 광고(class="cZnHG") 제외
            if "cZnHG" not in place.get_attribute("class"):
                if name not in real_places:
                    real_places.append(name)
        except Exception:
            continue

def get_place_rank(keyword, target_place="무궁 청라점"):
    real_places.clear()
    driver.get(f"https://map.naver.com/v5/search/{keyword}")

    # 검색 iframe 로딩 대기
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[@id='searchIframe']"))
        )
        iframe = driver.find_element(By.XPATH, "//*[@id='searchIframe']")
        driver.switch_to.frame(iframe)
    except TimeoutException:
        print(f"🚨 '{keyword}' 검색 실패: 페이지 로딩 시간 초과")
        return None

    # 페이지 버튼 갯수 확인
    try:
        page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
        total_pages = len(page_buttons) if page_buttons else 1
    except Exception:
        total_pages = 1

    # 최대 5페이지 탐색
    for page_num in range(1, min(total_pages, 5) + 1):
        get_places_from_page()

        if page_num < total_pages:
            go_to_next_page(page_num)

    # 순위 찾기
    if target_place in real_places:
        return real_places.index(target_place) + 1
    return None

# --- Batch Update Preparation ---
# Define the starting row and the columns to update
start_row = 55
end_row = 80
column_rank = 4  # Column D
column_keyword = 5  # Column E

# Initialize a list to hold the update data
update_data = []

# 메인 로직
for i, keyword in enumerate(keywords, start=start_row):
    try:
        rank = get_place_rank(keyword)
        if rank:
            print(f"✅ '{keyword}'의 순위는 {rank}")
            update_data.append([rank, keyword])
        else:
            print(f"🚨 '{keyword}'의 순위를 찾지 못했습니다.")
            update_data.append(["검색결과없음", keyword])
    except Exception as e:
        print(f"🚨 '{keyword}' 처리 중 오류: {str(e)}")
        update_data.append(["오류 발생", keyword])

# Define the range for batch update (e.g., "D55:E80")
update_range = f"D{start_row}:E{end_row}"

# Perform the batch update
try:
    sheet.update(update_range, update_data)
    print("✅ Google Sheets에 배치 업데이트 완료")
except Exception as e:
    print(f"🚨 배치 업데이트 중 오류 발생: {e}")

driver.quit()
print("✅ 모든 키워드 순위 업데이트 완료")

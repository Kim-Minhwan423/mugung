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

# 반드시 /tmp/keyfile.json 으로 바꿔줘야 Actions에서 정상 작동
json_path = "/tmp/keyfile.json"
creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
client = gspread.authorize(creds)

# 스프레드시트 열기
spreadsheet = client.open("청라 일일/월말 정산서")  # 예시
sheet = spreadsheet.worksheet("체험단&예약")        # 예시

# === (5) 세션 안정성: Headless / No-Sandbox / dev-shm / GPU 비활성 ===
options = webdriver.ChromeOptions()
options.add_argument("--headless")          # GUI 없이 동작
options.add_argument("--no-sandbox")        # 권한 문제 방지
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920x1080")
options.add_argument(f"user-agent={user_agent}")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

# 키워드
keywords = sheet.col_values(2)[54:80]

# 광고 제외 플레이스 목록
real_places = []

# =============== (1) 스크롤 방식 개선 ===============
def robust_scroll():
    """
    스크롤을 여러 번 시도해서, 최대한 많은 place 요소를 불러오는 함수.
    """
    try:
        scroll_container = driver.find_element(By.XPATH, "//*[@id='_pcmap_list_scroll_container']")
    except NoSuchElementException:
        print("🚨 스크롤 컨테이너를 찾지 못했습니다.")
        return []

    previous_count = 0
    max_attempts = 20  # 최대 스크롤 시도 횟수
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
        time.sleep(1.5)  # 스크롤 후 약간 대기

    # 최종 수집된 place 요소 반환
    return scroll_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")

# =============== (2) 페이지 전환 안정화 ===============
def go_to_next_page(page_idx):
    """
    page_idx에 해당하는 페이지 버튼을 누르고, 로딩을 기다린다.
    """
    try:
        # 페이지 버튼이 나타날 때까지 대기 (5초)
        WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.zRM9F > a"))
        )
        buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")

        if page_idx < len(buttons):
            driver.execute_script("arguments[0].click();", buttons[page_idx])
            time.sleep(3)  # 페이지 전환 후 로딩 시간
        else:
            print(f"🚨 page_idx={page_idx}가 버튼 범위 밖입니다.")
    except Exception as e:
        print(f"🚨 다음 페이지 이동 실패: {e}")

def get_places_from_page():
    """
    robust_scroll()를 통해 스크롤 후, 광고 제외한 플레이스 이름을 real_places에 추가
    """
    place_elements = robust_scroll()

    for place in place_elements:
        try:
            name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text.strip()
            if not name:
                continue
            # 광고 클래스 "cZnHG" 제외
            if "cZnHG" not in place.get_attribute("class"):
                if name not in real_places:
                    real_places.append(name)
        except Exception:
            # 광고나 예외는 무시
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

    # 최대 5페이지까지만 탐색
    for page_num in range(1, min(total_pages, 5) + 1):
        # 스크롤 후 플레이스 수집
        get_places_from_page()

        # 다음 페이지 클릭 (마지막 페이지는 클릭 안 함)
        if page_num < total_pages:
            go_to_next_page(page_num)  # page_num에 해당하는 버튼 클릭

    # 순위 찾기
    if target_place in real_places:
        return real_places.index(target_place) + 1
    return None

# 메인 로직: 키워드별 순위 가져오기
for i, keyword in enumerate(keywords, start=55):
    try:
        rank = get_place_rank(keyword)
        if rank:
            print(f"✅ '{keyword}'의 순위는 {rank}")
            sheet.update_cell(i, 4, rank)
            sheet.update_cell(i, 5, keyword)
        else:
            print(f"🚨 '{keyword}'의 순위를 찾지 못했습니다.")
            sheet.update_cell(i, 4, "검색결과없음")
            sheet.update_cell(i, 5, keyword)
    except Exception as e:
        print(f"🚨 '{keyword}' 처리 중 오류: {str(e)}")
        sheet.update_cell(i, 4, "오류 발생")

driver.quit()
print("✅ 모든 키워드 순위 업데이트 완료")

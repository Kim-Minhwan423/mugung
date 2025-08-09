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

# =========================
# 설정
# =========================
TARGET_PLACE = "무궁 송도점"  # 순위 확인 대상 가게명

# 모바일 User-Agent (모바일 DOM을 강제)
user_agent = (
    "Mozilla/5.0 (Linux; Android 10; SM-G973N) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)

# Google Sheets API 인증
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
json_path = "/tmp/keyfile.json"  # 서비스 계정 키 경로
creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
client = gspread.authorize(creds)

spreadsheet = client.open("송도 일일/월말 정산서")
sheet = spreadsheet.worksheet("예약&마케팅")

# =========================
# Selenium 초기화 (모바일/헤드리스)
# =========================
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--disable-software-rasterizer")
options.add_argument("--remote-debugging-port=9222")
options.add_argument("--lang=ko-KR")
options.add_argument("--window-size=412,915")  # 모바일 화면 비율(갤럭시S급)
options.add_argument(f"user-agent={user_agent}")
options.page_load_strategy = "eager"

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)
driver.set_page_load_timeout(40)

# =========================
# 유틸/헬퍼
# =========================
def switch_into_search_iframe(driver, timeout=40):
    """
    모바일/데스크톱 혼재 환경에서 search iframe이 있으면 진입.
    없으면 False 반환 (최상위 DOM에서 리스트가 바로 있을 수 있음).
    """
    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    iframe_xpaths = [
        "//*[@id='searchIframe']",
        "//*[@id='ct']//iframe[contains(@src, 'search')]",
        "//iframe[contains(@src, '/search2/')]"
    ]
    for _ in range(timeout):
        for xp in iframe_xpaths:
            try:
                iframe = driver.find_element(By.XPATH, xp)
                driver.switch_to.frame(iframe)
                return True
            except NoSuchElementException:
                continue
        time.sleep(1)
    return False


def robust_scroll_mobile_first():
    """
    모바일/데스크톱 겸용 스크롤 로딩:
    - 리스트 컨테이너 후보 중 존재하는 것을 선택
    - 아이템 셀렉터 후보 중 존재하는 것으로 수집
    - 더 이상 아이템 수가 늘지 않을 때까지 맨 끝까지 스크롤
    """
    container_candidates = [
        "#_search_list_scroll_container",  # 모바일
        "#_pcmap_list_scroll_container",   # 데스크톱
        "div#ct",                          # 일부 모바일 레이아웃 fallback
        "div[data-nclick*='place']"        # 최후 fallback
    ]
    scroll_container = None
    for sel in container_candidates:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            scroll_container = el
            break
        except NoSuchElementException:
            continue

    if not scroll_container:
        print("🚨 리스트 컨테이너를 찾지 못했습니다.")
        return []

    item_selectors = [
        "li.UEzoS.rTjJo",   # 데스크톱 v5
        "li._item",         # 모바일 구버전
        "li"                # 최후 fallback
    ]

    previous_count = 0
    max_attempts = 60
    attempts = 0

    while attempts < max_attempts:
        places = []
        for item_css in item_selectors:
            try:
                places = scroll_container.find_elements(By.CSS_SELECTOR, item_css)
            except Exception:
                places = []
            if places:
                break

        current_count = len(places)
        if current_count == 0:
            # 첫 로딩 지연일 수 있으니 약간 대기 후 재시도
            time.sleep(1.0)
        if current_count == previous_count and current_count > 0:
            # 증가 없음 → 종료
            break

        if places:
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", places[-1])
            except WebDriverException as e:
                print(f"🚨 스크롤 중 오류: {e}")
                break

        previous_count = current_count
        attempts += 1
        time.sleep(1.0)

    # 최종 아이템 다시 수집
    final_places = []
    for item_css in item_selectors:
        try:
            final_places = scroll_container.find_elements(By.CSS_SELECTOR, item_css)
        except Exception:
            final_places = []
        if final_places:
            break

    return final_places


real_places = []  # 한 번의 검색에서 수집되는 가게명 목록

def get_places_from_page():
    """
    스크롤 로딩을 통해 현재 페이지의 모든 결과를 수집하고 real_places에 가게명을 누적.
    """
    place_elements = robust_scroll_mobile_first()

    # 가게명 후보 셀렉터들 (환경별 상이)
    name_selectors = [
        "span.TYaxT",      # 데스크톱 v5
        "strong._title",   # 모바일 구버전
        "span.OXiLu",      # 케이스 대응
        "a span"           # fallback
    ]

    for place in place_elements:
        name_text = ""
        for ns in name_selectors:
            try:
                txt = place.find_element(By.CSS_SELECTOR, ns).text.strip()
                if txt:
                    name_text = txt
                    break
            except Exception:
                continue

        if not name_text:
            # 요소 자체 텍스트에서 1줄 시도
            try:
                name_text = place.text.strip().split("\n")[0]
            except Exception:
                name_text = ""

        # 광고 카드 등 특정 클래스를 제외하고 싶다면 여기서 필터 가능
        if name_text and name_text not in real_places:
            real_places.append(name_text)


def get_place_rank(keyword, target_place=TARGET_PLACE):
    """
    모바일 검색 페이지로 접속 → (iframe 있으면 진입) → 스크롤 수집 → 대상 가게 순위 반환
    """
    real_places.clear()

    # 모바일 검색 URL (v5 스타일)
    # 쿼리는 URL 인코딩을 브라우저가 해주므로 그대로 전달해도 무방
    url = f"https://m.map.naver.com/search2/search.naver?query={keyword}&sm=hty&style=v5"
    driver.get(url)

    # iframe이 있으면 진입 (없어도 동작)
    _ = switch_into_search_iframe(driver, timeout=40)

    # 모바일은 페이지 버튼이 없거나 불안정 → 스크롤로 전부 로딩
    get_places_from_page()

    if target_place in real_places:
        return real_places.index(target_place) + 1
    return None


# =========================
# 키워드 불러오기 및 배치 업데이트
# =========================
# B83 ~ B200 범위를 넉넉히 읽고, 내용이 있는 셀만 처리
keywords = [kw.strip() for kw in sheet.col_values(2)[82:200] if kw.strip()]

start_row = 83   # 결과 기록 시작 행 (E83)
column_rank = 5  # E열
update_data = []

for idx, keyword in enumerate(keywords, start=start_row):
    try:
        rank = get_place_rank(keyword)
        if rank:
            print(f"✅ '{keyword}'의 순위는 {rank}")
            update_data.append([rank])
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

try:
    driver.quit()
except Exception:
    pass

print("✅ 모든 키워드 순위 업데이트 완료")

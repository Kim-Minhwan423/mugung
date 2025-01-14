import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# User-Agent 설정
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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
spreadsheet = client.open("송도 일일/월말 정산서")  # 예시
sheet = spreadsheet.worksheet("체험단&예약")        # 예시

options = webdriver.ChromeOptions()
options.add_argument("--headless")               # 헤드리스(화면 없이) 모드
options.add_argument("--no-sandbox")             # 샌드박스 비활성 (권한 문제 방지)
options.add_argument("--disable-dev-shm-usage")  # /dev/shm 용량 부족 문제 방지
options.add_argument("--disable-gpu")            # GPU 비활성
options.add_argument("--window-size=1920x1080")
options.add_argument(f"user-agent={user_agent}")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

# 키워드 (예: B55 ~ B80)
keywords = sheet.col_values(2)[54:80]

# 최종 데이터 저장 리스트 (광고 제외)
real_places = []

def get_places_from_page():
    previous_height = 0
    while True:
        try:
            places_container = driver.find_element(By.XPATH, "//*[@id='_pcmap_list_scroll_container']")
            places = places_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")
            current_height = len(places)

            if current_height == previous_height:
                break

            previous_height = current_height
            driver.execute_script("arguments[0].scrollIntoView();", places[-1])
            time.sleep(1)
        except (NoSuchElementException, WebDriverException):
            print("🚨 스크롤 오류 발생")
            break

    for place in places:
        try:
            name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text
            if not name:
                continue
            # 광고를 의미하는 클래스명 "cZnHG"가 없는 경우만
            if "cZnHG" not in place.get_attribute("class"):
                if name not in real_places:
                    real_places.append(name)
        except Exception:
            continue

def get_place_rank(keyword, target_place="무궁 송도점"):
    real_places.clear()
    driver.get(f"https://map.naver.com/v5/search/{keyword}")

    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//*[@id='searchIframe']")))
        driver.switch_to.frame(driver.find_element(By.XPATH, "//*[@id='searchIframe']"))
    except TimeoutException:
        print(f"🚨 '{keyword}' 검색 실패: 페이지 로딩 시간 초과")
        return None

    try:
        page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
        total_pages = len(page_buttons) if page_buttons else 1
    except Exception:
        total_pages = 1

    for page_num in range(1, min(total_pages, 5) + 1):
        try:
            get_places_from_page()
            if page_num < total_pages:
                page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
                if page_num < len(page_buttons):
                    next_page_button = page_buttons[page_num]
                    driver.execute_script("arguments[0].click();", next_page_button)
                    time.sleep(1)
        except (TimeoutException, NoSuchElementException) as e:
            print(f"🚨 다음 페이지 이동 실패: {str(e)}")
            break

    if target_place in real_places:
        return real_places.index(target_place) + 1
    return None

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

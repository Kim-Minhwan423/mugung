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

# =======================
# [1] Google Sheets API 인증
# =======================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# GitHub Actions에서 secrets를 통해 "/tmp/keyfile.json" 경로에 임시 파일을 생성한다고 가정
json_path = "/tmp/keyfile.json"

creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
client = gspread.authorize(creds)

# 원하는 스프레드시트/시트 열기 (예시)
spreadsheet = client.open("청라 일일/월말 정산서")  
sheet = spreadsheet.worksheet("체험단&예약")  

# =======================
# [2] Selenium 환경 설정
# =======================
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
options = webdriver.ChromeOptions()
options.add_argument(f"user-agent={user_agent}")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920x1080")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# =======================
# [3] 스프레드시트에서 키워드 가져오기
# =======================
keywords = sheet.col_values(2)[54:80]  # 예: B55 ~ B80

# '무궁 청라점'을 찾는다고 가정
target_place_name = "무궁 청라점"

# 광고 제외 플레이스 이름을 담을 리스트
real_places = []

# =======================
# [4] 광고 제외 플레이스 스크롤/크롤링 함수
# =======================
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
            time.sleep(1)  # 스크롤 후 잠시 대기
        except (NoSuchElementException, WebDriverException):
            print("🚨 스크롤 중 오류 발생")
            break

    for place in places:
        try:
            name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text
            # 광고는 place의 class에 "cZnHG"가 포함됨
            if name and "cZnHG" not in place.get_attribute("class"):
                if name not in real_places:
                    real_places.append(name)
        except Exception:
            continue

# =======================
# [5] 페이지별 크롤링 & 순위 확인 함수
# =======================
def get_place_rank(keyword, target_place=target_place_name):
    real_places.clear()
    # 네이버 지도 검색
    driver.get(f"https://map.naver.com/v5/search/{keyword}")
    
    # 검색 iframe 로드 대기
    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//*[@id='searchIframe']")))
        driver.switch_to.frame(driver.find_element(By.XPATH, "//*[@id='searchIframe']"))
    except TimeoutException:
        print(f"🚨 '{keyword}' 검색 실패: 페이지 로딩 시간 초과.")
        return None

    # 페이지 개수 확인
    try:
        page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
        total_pages = len(page_buttons) if page_buttons else 1
    except Exception:
        total_pages = 1

    # 최대 5페이지까지 광고 제외 플레이스 이름을 수집
    for page_num in range(1, min(total_pages, 5) + 1):
        try:
            get_places_from_page()

            # 다음 페이지로 넘어가기
            if page_num < total_pages:
                page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
                if page_num < len(page_buttons):
                    next_page_button = page_buttons[page_num]
                    driver.execute_script("arguments[0].click();", next_page_button)
                    time.sleep(1)  # 페이지 전환 후 잠시 대기
        except (TimeoutException, NoSuchElementException) as e:
            print(f"🚨 다음 페이지 이동 실패: {str(e)}")
            break

    # 순위 찾기
    if target_place in real_places:
        return real_places.index(target_place) + 1
    return None

# =======================
# [6] 메인 루틴: 키워드 순회 & 결과 저장
# =======================
for i, keyword in enumerate(keywords, start=55):
    try:
        rank = get_place_rank(keyword)
        if rank:
            print(f"✅ '{keyword}' 순위: {rank}")
            sheet.update_cell(i, 4, rank)  # D열
            sheet.update_cell(i, 5, keyword)  # E열
        else:
            print(f"🚨 '{keyword}'의 순위를 찾지 못했습니다.")
            sheet.update_cell(i, 4, "검색결과없음")
            sheet.update_cell(i, 5, keyword)
    except Exception as e:
        print(f"🚨 '{keyword}' 처리 중 오류: {str(e)}")
        sheet.update_cell(i, 4, "오류 발생")

# =======================
# [7] 종료
# =======================
driver.quit()
print("✅ 모든 키워드 순위 업데이트 완료!")


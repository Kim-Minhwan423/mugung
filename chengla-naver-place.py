import os
import json
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException

def setup_chrome_driver():
    """ChromeDriver와 Chrome 설정"""
    options = Options()
    options.add_argument("--headless")  # UI 없이 실행
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.binary_location = "/usr/bin/google-chrome"  # Google Chrome 경로

    service = Service("/usr/local/bin/chromedriver")  # ChromeDriver 경로
    return webdriver.Chrome(service=service, options=options)

# ✅ ChromeDriver 설정
try:
    driver = setup_chrome_driver()
    print("✅ Chrome 실행 성공")
except Exception as e:
    print(f"🚨 Chrome 실행 실패: {e}")
    raise

# ✅ 환경 변수에서 Google 인증 파일 가져오기
json_keyfile_content = os.getenv('GOOGLE_CREDENTIALS')
if json_keyfile_content is None:
    raise ValueError("환경 변수 'GOOGLE_CREDENTIALS'가 설정되지 않았습니다.")

json_keyfile_dict = json.loads(json_keyfile_content)

# ✅ Google Sheets API 인증
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_keyfile_dict, scope)
client = gspread.authorize(creds)

# ✅ 구글 스프레드시트 열기
spreadsheet = client.open("청라 일일/월말 정산서")
sheet = spreadsheet.worksheet("체험단&예약")

# ✅ 크롤링할 키워드 가져오기 (B55~B80)
keywords = sheet.col_values(2)[54:80]

# ✅ 광고를 제외한 순수 플레이스 리스트
real_places = []

# 📝 광고 제외 후 플레이스 목록 확보 함수
def get_places_from_page():
    previous_height = 0
    while True:
        try:
            places_container = driver.find_element(By.XPATH, "//*[@id='_pcmap_list_scroll_container']")
            places = places_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")
            current_height = len(places)

            if current_height == previous_height:
                break  # 더 이상 변화가 없으면 종료

            previous_height = current_height
            driver.execute_script("arguments[0].scrollIntoView();", places[-1])
            time.sleep(1)
        except (NoSuchElementException, WebDriverException):
            break

    for place in places:
        try:
            name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text
            if name and "cZnHG" not in place.get_attribute("class"):  # 광고 제외
                if name not in real_places:  # 중복 방지
                    real_places.append(name)
        except Exception:
            continue

# 🔄 1~5페이지 네이버 플레이스 크롤링
def get_place_rank(keyword, target_place="무궁 청라점"):
    real_places.clear()
    driver.get(f"https://map.naver.com/v5/search/{keyword}")

    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//*[@id='searchIframe']")))
        driver.switch_to.frame(driver.find_element(By.XPATH, "//*[@id='searchIframe']"))
    except TimeoutException:
        print(f"🚨 '{keyword}' 검색 실패: 페이지 로딩 시간 초과")
        return None

    # 페이지 개수 확인
    try:
        page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
        total_pages = len(page_buttons) if page_buttons else 1
    except Exception:
        total_pages = 1

    # 최대 5페이지까지 크롤링
    for page_num in range(1, min(total_pages, 5) + 1):
        try:
            get_places_from_page()
            if page_num < total_pages:
                page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
                if page_num < len(page_buttons):
                    driver.execute_script("arguments[0].click();", page_buttons[page_num])
                    time.sleep(1)
        except (TimeoutException, NoSuchElementException):
            break

    # '무궁 청라점' 순위 찾기
    return real_places.index(target_place) + 1 if target_place in real_places else None

# ✅ 키워드별 순위 가져와서 구글 시트 업데이트
for i, keyword in enumerate(keywords, start=55):
    try:
        rank = get_place_rank(keyword)

        if rank:
            print(f"✅ '{keyword}'의 순위는 {rank}위")
            sheet.update_cell(i, 4, rank)  # D열에 순위 입력
            sheet.update_cell(i, 5, keyword)  # E열에 키워드 입력
        else:
            print(f"🚨 '{keyword}'의 검색 결과 없음")
            sheet.update_cell(i, 4, "검색결과없음")
            sheet.update_cell(i, 5, keyword)
    except Exception as e:
        print(f"🚨 '{keyword}' 처리 중 오류 발생: {str(e)}")
        sheet.update_cell(i, 4, "오류 발생")

# ✅ 브라우저 종료
driver.quit()
print("✅ 모든 키워드 순위 업데이트 완료")

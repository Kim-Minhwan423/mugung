from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from webdriver_manager.chrome import ChromeDriverManager
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
import os
from oauth2client.service_account import ServiceAccountCredentials

# 🛠 User-Agent 설정
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 환경 변수에서 인증 파일 경로 가져오기
json_keyfile_path = os.getenv('GOOGLE_CREDENTIALS')

# Google Sheets API 인증
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(json_keyfile_path, scope)
client = gspread.authorize(creds)

# 구글 스프레드시트 열기
spreadsheet = client.open("청라 일일/월말 정산서")  # 스프레드시트 이름
sheet = spreadsheet.worksheet("체험단&예약")  # '체험단&예약' 시트 선택

# Chrome WebDriver 실행
options = webdriver.ChromeOptions()
options.add_argument(f"user-agent={user_agent}")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920x1080")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# 🔍 키워드(B55~B80) 가져와서 네이버 지도 검색 페이지에 쳐 넣기
keywords = sheet.col_values(2)[54:80]  # B55부터 B80까지

# ✅ 최종 데이터 저장 리스트 (광고 제외한 순수 플레이스 목록)
real_places = []

# 📝 광고를 제외한 페이지별 플레이스 확보 함수
def get_places_from_page():
    previous_height = 0
    while True:
        try:
            # 현재 로드된 플레이스 개수 확인
            places_container = driver.find_element(By.XPATH, "//*[@id='_pcmap_list_scroll_container']")
            places = places_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")
            current_height = len(places)

            # 더 이상 변화가 없으면 종료
            if current_height == previous_height:
                break

            previous_height = current_height
            driver.execute_script("arguments[0].scrollIntoView();", places[-1])
            time.sleep(1)  # 스크롤 후 대기
        except (NoSuchElementException, WebDriverException) as e:
            print(f"🚨 오류 발생: {str(e)}")
            break

    # 광고를 제외한 플레이스만 별도 리스트에 저장
    for place in places:
        try:
            name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text
            if not name:
                continue
            
            # 광고(cZnHG 클래스 포함)인지 확인 후, 일반 플레이스만 저장
            if "cZnHG" not in place.get_attribute("class"):
                if name not in real_places:  # 중복 방지
                    real_places.append(name)
        except Exception:
            continue

# 🔄 1~5페이지 플레이스 크롤링 (동적 페이지 개수 감지)
def get_place_rank(keyword, target_place="무궁 청라점"):
    real_places.clear()  # 일반 플레이스 초기화
    driver.get(f"https://map.naver.com/v5/search/{keyword}")

    # ⏳ 페이지가 완전히 로드될 때까지 대기
    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//*[@id='searchIframe']")))
        driver.switch_to.frame(driver.find_element(By.XPATH, "//*[@id='searchIframe']"))
    except TimeoutException:
        print(f"🚨 '{keyword}' 검색 실패: 페이지 로딩 시간 초과. 재시도합니다.")
        return None  # 오류 시 종료

    # ⭐ 페이지 개수 동적 감지 ⭐
    try:
        page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
        total_pages = len(page_buttons)  # 페이지 개수 확인
    except Exception:
        total_pages = 1  # 예외 발생 시 최소 1페이지는 있다고 가정

    # 페이지별로 크롤링
    for page_num in range(1, min(total_pages, 5) + 1):  # 최대 5페이지까지 크롤링
        try:
            get_places_from_page()

            # 다음 페이지 버튼 클릭 (마지막 페이지는 클릭 X)
            if page_num < total_pages:
                page_buttons = driver.find_elements(By.CSS_SELECTOR, "div.zRM9F > a")
                
                if page_num < len(page_buttons):  
                    next_page_button = page_buttons[page_num]  # 정확한 페이지 버튼 선택
                    driver.execute_script("arguments[0].click();", next_page_button)  # JS로 클릭 (더 정확함)                    
                    time.sleep(1)  # 페이지 전환 후 대기
        except (TimeoutException, NoSuchElementException) as e:
            print(f"🚨 다음 페이지 이동 실패: {str(e)}")
            break  # 다음 페이지가 없으면 중단

    # '무궁 청라점' 순위 찾기 (광고 제외한 real_places 기준)
    if target_place in real_places:
        return real_places.index(target_place) + 1
    return None  # 원하는 장소를 찾지 못한 경우

# 키워드에 대한 순위 가져오기 및 기록하기
for i, keyword in enumerate(keywords, start=55):
    try:
        rank = get_place_rank(keyword)

        if rank:
            print(f"✅ '{keyword}'의 순위는 {rank}입니다.")
            sheet.update_cell(i, 4, rank)  # D열에 순위 업데이트
            sheet.update_cell(i, 5, keyword)  # E열에 키워드 입력
        else:
            print(f"🚨 '{keyword}'에 대한 순위를 찾을 수 없습니다.")
            sheet.update_cell(i, 4, "검색결과없음")  # 순위를 찾지 못한 경우 D열에 "검색결과없음" 입력
            sheet.update_cell(i, 5, keyword)  # E열에 키워드 입력
    except Exception as e:
        print(f"🚨 '{keyword}' 처리 중 오류 발생: {str(e)}")
        sheet.update_cell(i, 4, "오류 발생")  # 오류 발생 시 "오류 발생" 표시

# 브라우저 종료
driver.quit()

print("✅ 모든 키워드에 대한 순위 업데이트 완료")

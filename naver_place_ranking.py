from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

def get_naver_place_ranking(keyword):
    # Chrome 헤드리스 모드로 실행
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    
    # Selenium WebDriver 설정
    driver = webdriver.Chrome(options=options)

    try:
        # 네이버 플레이스 검색 URL
        url = f"https://m.place.naver.com/search/{keyword}/place"  # 키워드에 맞는 URL로 변경
        driver.get(url)
        time.sleep(3)  # 페이지 로딩을 위한 대기시간

        # 순위 정보 가져오기 (여기서는 예시로 첫 30개의 순위만 가져옴)
        rank_data = []
        places = driver.find_elements(By.CSS_SELECTOR, "div.place_item")  # 순위 정보가 담긴 요소
        for place in places[:30]:
            name = place.find_element(By.CSS_SELECTOR, "span.place_name").text
            rank_data.append(name)
        
        return rank_data
    except Exception as e:
        raise Exception(f"Error fetching naver rank: {str(e)}")
    finally:
        driver.quit()

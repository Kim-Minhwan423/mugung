from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time

app = Flask(__name__)

@app.route('/naver-rank', methods=['GET'])
def get_naver_place_rank():
    keyword = request.args.get('keyword')
    if not keyword:
        return jsonify({"error": "Keyword is required"}), 400

    # 🛠 User-Agent 설정
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    # Chrome WebDriver 실행
    options = Options()
    options.add_argument(f"user-agent={user_agent}")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    # 🔍 네이버 지도 검색 페이지 열기
    driver.get(f"https://map.naver.com/v5/search/{keyword}")

    # ⏳ 페이지가 완전히 로드될 때까지 대기
    time.sleep(5)

    # 🖼️ iframe 내부로 전환
    driver.switch_to.frame(driver.find_element(By.XPATH, "//*[@id='searchIframe']"))
    
    # ✅ 최종 데이터 저장 리스트
    all_places = []

    # 📝 페이지별 플레이스 확보 함수 (광고 제외, <span class="TYaxT"> 요소만 출력)
    def get_places_from_page():
        previous_height = 0
        while True:
            places_container = driver.find_element(By.XPATH, "//*[@id='_pcmap_list_scroll_container']")
            places = places_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")
            current_height = len(places)

            if current_height == previous_height:
                break

            previous_height = current_height
            driver.execute_script("arguments[0].scrollIntoView();", places[-1])
            time.sleep(2)

        # 광고 제외 후 <span class="TYaxT"> 요소만 추출
        for place in places:
            if "cZnHG" in place.get_attribute("class"):  # 광고인지 확인
                continue
            try:
                name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text
                if name and name not in all_places:  # 중복 제거
                    all_places.append(name)
            except:
                continue

    # 🔄 1~5페이지 플레이스 크롤링
    get_places_from_page()

    # 브라우저 종료
    driver.quit()

    # 최종 결과 반환
    return jsonify({"rank": all_places[:300]})

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)

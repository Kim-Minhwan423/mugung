from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

app = Flask(__name__)

# 기본 루트 엔드포인트
@app.route('/')
def home():
    return "Naver Place API is running!"

# 네이버 플레이스 순위 크롤링 API
@app.route('/get_naver_place_rank', methods=['GET'])
def get_naver_place_rank():
    keyword = request.args.get('keyword')
    if not keyword:
        return jsonify({'error': 'Keyword parameter is required'}), 400

    # Chrome WebDriver 설정
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # GUI 없이 실행
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # 네이버 플레이스 검색 URL
    search_url = f"https://map.naver.com/v5/search/{keyword}"
    driver.get(search_url)
    time.sleep(3)  # 페이지 로딩 대기

    # iframe 내부로 이동
    driver.switch_to.frame("searchIframe")

    # 플레이스 목록 가져오기
    places = driver.find_elements(By.CSS_SELECTOR, "div.YjdnP > div > div > span.TYaxT")

    results = []
    for idx, place in enumerate(places[:300], start=1):  # 최대 300위까지 저장
        results.append({'rank': idx, 'name': place.text})

    driver.quit()

    return jsonify({'keyword': keyword, 'results': results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

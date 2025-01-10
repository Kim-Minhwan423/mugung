from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

@app.route("/get_naver_place_rank", methods=["GET"])
def get_naver_place_rank():
    # URL 파라미터로 키워드를 받음
    keyword = request.args.get("keyword")
    
    # Chrome 옵션 설정
    options = Options()
    options.binary_location = "/usr/bin/google-chrome"  # Chrome 실행 경로
    options.add_argument("--headless")  # 헤드리스 모드
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # ChromeDriver 설정
    service = Service(ChromeDriverManager().install())  # 자동으로 ChromeDriver 관리
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # 네이버 플레이스 검색 URL로 이동
        driver.get(f"https://m.place.naver.com/search/{keyword}")
        
        # 여기서 필요한 데이터 추출을 위한 코드 추가 (예: 무한 스크롤 구현, 특정 요소 추출 등)
        # 예시로 페이지 타이틀을 반환합니다.
        page_title = driver.title
        
        return jsonify({"keyword": keyword, "page_title": page_title})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        # 브라우저 종료
        driver.quit()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

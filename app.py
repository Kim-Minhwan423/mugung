from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

@app.route('/naver-rank', methods=['GET'])
def get_naver_rank():
    keyword = request.args.get("keyword")
    if not keyword:
        return jsonify({"error": "키워드를 입력해주세요!"}), 400

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    url = f"https://map.naver.com/v5/search/{keyword}"
    driver.get(url)
    time.sleep(5)

    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//*[@id='searchIframe']")))
        driver.switch_to.frame(driver.find_element(By.XPATH, "//*[@id='searchIframe']"))
    except Exception as e:
        driver.quit()
        return jsonify({"error": "iframe을 찾을 수 없습니다.", "details": str(e)}), 500

    all_places = []
    
    def get_places_from_page():
        places_container = driver.find_element(By.XPATH, "//*[@id='_pcmap_list_scroll_container']")
        places = places_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")

        for place in places:
            if "cZnHG" in place.get_attribute("class"):  # 광고 제외
                continue
            try:
                name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text
                if name and name not in all_places:
                    all_places.append(name)
            except:
                continue

    for _ in range(5):  # 1~5페이지 크롤링
        get_places_from_page()
        try:
            next_page_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#app-root > div > div.XUrfU > div.zRM9F > a:nth-child(7)"))
            )
            next_page_button.click()
            time.sleep(5)
        except:
            break

    driver.quit()

    return jsonify({"keyword": keyword, "rankings": all_places[:300]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

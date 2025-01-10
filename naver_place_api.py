from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

def get_naver_place_rank(keyword, target_name):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(f"https://map.naver.com/v5/search/{keyword}")

    time.sleep(5)  # 페이지 로딩 대기

    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//*[@id='searchIframe']")))
        driver.switch_to.frame(driver.find_element(By.XPATH, "//*[@id='searchIframe']"))
    except Exception as e:
        driver.quit()
        return {"error": "iframe을 찾을 수 없음"}

    all_places = []
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

    for idx, place in enumerate(places, start=1):
        if "cZnHG" in place.get_attribute("class"):  # 광고 제외
            continue
        try:
            name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text
            if name == target_name:
                driver.quit()
                return {"keyword": keyword, "rank": idx, "place": target_name}
        except:
            continue

    driver.quit()
    return {"keyword": keyword, "rank": "Not Found", "place": target_name}

@app.route("/get_rank", methods=["GET"])
def get_rank():
    keyword = request.args.get("keyword")
    target_name = request.args.get("target", "무궁 청라점")
    if not keyword:
        return jsonify({"error": "keyword parameter is required"}), 400
    
    result = get_naver_place_rank(keyword, target_name)
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

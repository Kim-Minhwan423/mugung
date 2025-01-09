from flask import Flask, jsonify, request
from selenium import webdriver
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

def get_places_from_keyword(keyword):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    driver.get(f"https://map.naver.com/v5/search/{keyword}")
    time.sleep(5)
    
    places = []
    try:
        places_container = driver.find_element(By.XPATH, "//*[@id='_pcmap_list_scroll_container']")
        place_elements = places_container.find_elements(By.CSS_SELECTOR, "li.UEzoS.rTjJo")
        for place in place_elements[:10]:  # 1~10위만 가져오기
            name = place.find_element(By.CSS_SELECTOR, "span.TYaxT").text
            places.append(name)
    except Exception as e:
        print(f"Error: {e}")
    
    driver.quit()
    return places

@app.route('/places', methods=['GET'])
def places():
    keyword = request.args.get('keyword')
    if keyword:
        places = get_places_from_keyword(keyword)
        return jsonify({'data': places})
    else:
        return jsonify({'error': 'Keyword is required'}), 400

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)

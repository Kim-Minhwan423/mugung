from flask import Flask, request, jsonify
from naver_place_ranking import get_naver_place_ranking

app = Flask(__name__)

@app.route('/naver-rank')
def naver_rank():
    keyword = request.args.get('keyword')  # 쿼리 파라미터로 전달된 키워드
    if not keyword:
        return jsonify({"error": "Keyword is required"}), 400
    
    # 네이버 플레이스 순위 가져오는 코드 호출
    try:
        rank_data = get_naver_place_ranking(keyword)
        return jsonify({"rank": rank_data})  # rank_data는 순위 정보
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)

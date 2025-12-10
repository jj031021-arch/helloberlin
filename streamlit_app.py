import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
import google.generativeai as genai
import googlemaps
import plotly.express as px
import streamlit.components.v1 as components  # 웹사이트 임베딩용

# ---------------------------------------------------------
# 1. 설정 및 API 키 로드
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="베를린 풀코스 가이드")

GMAPS_API_KEY = st.secrets.get("google_maps_api_key", "")
GEMINI_API_KEY = st.secrets.get("gemini_api_key", "")

# 클라이언트 초기화
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except:
        pass

# ---------------------------------------------------------
# 2. 데이터 처리 함수 (OSM & 날씨 & 환율)
# ---------------------------------------------------------
@st.cache_data
def get_exchange_rate():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/EUR"
        data = requests.get(url).json()
        return data['rates']['KRW']
    except:
        return 1450.0

@st.cache_data
def get_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current_weather=true"
        data = requests.get(url).json()
        return data['current_weather']
    except:
        return {"temperature": 15.0, "weathercode": 0}

@st.cache_data
def get_osm_places(category, lat, lng, radius_m=3000, cuisine_filter=None):
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    if category == 'restaurant':
        tag = '["amenity"="restaurant"]'
    elif category == 'hotel':
        tag = '["tourism"="hotel"]'
    elif category == 'tourism':
        tag = '["tourism"~"attraction|museum|artwork|viewpoint"]'
    else:
        return []

    query = f"""
    [out:json];
    (
      node{tag}(around:{radius_m},{lat},{lng});
    );
    out body;
    """
    
    try:
        response = requests.get(overpass_url, params={'data': query})
        data = response.json()
        
        results = []
        for element in data['elements']:
            if 'tags' in element and 'name' in element['tags']:
                cuisine = element['tags'].get('cuisine', 'general').lower()
                name = element['tags']['name']
                
                place_type = "관광지"
                if category == 'restaurant':
                    if 'korean' in cuisine: place_type = "한식"
                    elif any(x in cuisine for x in ['burger', 'pizza', 'italian', 'french', 'german', 'american', 'steak']): place_type = "양식"
                    elif any(x in cuisine for x in ['chinese', 'vietnamese', 'thai', 'japanese', 'sushi', 'asian', 'indian']): place_type = "아시안"
                    elif any(x in cuisine for x in ['coffee', 'cafe', 'cake']): place_type = "카페"
                    else: place_type = "식당"
                        
                    if cuisine_filter and "전체" not in cuisine_filter: 
                        if place_type not in cuisine_filter: continue
                elif category == 'hotel':
                    place_type = "숙소"

                search_query = f"{name} Berlin".replace(" ", "+")
                google_link = f"https://www.google.com/search?q={search_query}"

                results.append({
                    "name": name,
                    "lat": element['lat'],
                    "lng": element['lon'],
                    "type": category,
                    "desc": place_type, 
                    "link": google_link
                })
        return results
    except Exception:
        return []

def get_gemini_response(prompt):
    if not GEMINI_API_KEY: return "API 키 확인 필요"
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except: return "AI 응답 오류"

def search_location(query):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {'q': query, 'format': 'json', 'limit': 1}
        headers = {'User-Agent': 'BerlinApp/1.0'}
        res = requests.get(url, params=params, headers=headers).json()
        if res:
            return float(res[0]['lat']), float(res[0]['lon']), res[0]['display_name']
    except:
        pass
    return None, None, None

# ---------------------------------------------------------
# 3. 여행 코스 데이터
# ---------------------------------------------------------
courses = {
    "🌳 Theme 1: 숲과 힐링 (티어가르텐)": [
        {"name": "1. 전승기념탑", "lat": 52.5145, "lng": 13.3501, "type": "view", "desc": "베를린 전경이 한눈에 보이는 황금 천사상"},
        {"name": "2. 티어가르텐 산책", "lat": 52.5135, "lng": 13.3575, "type": "walk", "desc": "도심 속 거대한 허파, 맑은 공기 마시기"},
        {"name": "3. Cafe am Neuen See", "lat": 52.5076, "lng": 13.3448, "type": "food", "desc": "호수 바로 앞, 피자와 맥주가 맛있는 비어가든"},
        {"name": "4. 베를린 동물원", "lat": 52.5079, "lng": 13.3377, "type": "view", "desc": "세계 최대 종을 보유한 역사 깊은 동물원"},
        {"name": "5. Monkey Bar", "lat": 52.5049, "lng": 13.3353, "type": "food", "desc": "동물원 원숭이를 내려다보며 칵테일 한잔"},
        {"name": "6. 카이저 빌헬름 교회", "lat": 52.5048, "lng": 13.3350, "type": "view", "desc": "전쟁의 참상을 기억하기 위해 보존된 교회"}
    ],
    "🎨 Theme 2: 예술과 고전 (박물관 섬)": [
        {"name": "1. 베를린 돔", "lat": 52.5190, "lng": 13.4010, "type": "view", "desc": "웅장한 돔 지붕 위에서 보는 시내 뷰"},
        {"name": "2. 구 국립 미술관", "lat": 52.5208, "lng": 13.3982, "type": "view", "desc": "그리스 신전 같은 외관과 19세기 회화"},
        {"name": "3. 제임스 사이먼 공원", "lat": 52.5213, "lng": 13.4005, "type": "walk", "desc": "슈프레 강변에 앉아 쉬어가는 핫플"},
        {"name": "4. Hackescher Hof", "lat": 52.5246, "lng": 13.4020, "type": "view", "desc": "아르누보 양식의 아름다운 8개 안뜰"},
        {"name": "5. Monsieur Vuong", "lat": 52.5244, "lng": 13.4085, "type": "food", "desc": "줄 서서 먹는 베트남 쌀국수 맛집"},
        {"name": "6. Zeit für Brot", "lat": 52.5265, "lng": 13.4090, "type": "food", "desc": "시나몬 롤이 입에서 녹는 베이커리"}
    ],
    "🏰 Theme 3: 분단의 역사 (장벽 투어)": [
        {"name": "1. 베를린 장벽 기념관", "lat": 52.5352, "lng": 13.3903, "type": "view", "desc": "장벽이 실제 모습 그대로 보존된 곳"},
        {"name": "2. Mauerpark", "lat": 52.5404, "lng": 13.4048, "type": "walk", "desc

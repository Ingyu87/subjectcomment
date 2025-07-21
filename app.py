# app.py
# 필요한 라이브러리들을 가져옵니다.
import streamlit as st
import json
import os
import google.generativeai as genai
import re

# --- 1. 기본 페이지 설정 ---
# 웹앱의 제목과 레이아웃을 설정합니다.
st.set_page_config(
    page_title="AI 교과평어 생성 도우미",
    page_icon="✍️",
    layout="wide",
)

# --- 2. 상태 관리 초기화 ---
# st.session_state는 사용자가 앱과 상호작용하는 동안 데이터를 기억하는 공간입니다.
if 'final_sentences' not in st.session_state:
    st.session_state.final_sentences = []
# '생성 시작' 버튼 클릭 상태를 저장하기 위한 변수
if 'start_generation' not in st.session_state:
    st.session_state.start_generation = False

# --- 3. Gemini API 키 설정 ---
# 스트림릿의 Secrets 관리 기능을 사용하여 API 키를 안전하게 불러옵니다.
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    # 사이드바에 API 키 로드 성공 메시지 표시
    st.sidebar.success("✅ Gemini API 키가 연결되었습니다.")
except Exception as e:
    # Secrets에 API 키가 없을 경우 에러 메시지 표시
    st.sidebar.error("⚠️ Gemini API 키를 등록해주세요.")
    st.error("사이드바에 Gemini API 키를 등록해야 앱을 사용할 수 있습니다.")
    st.stop() # API 키가 없으면 앱 실행 중지

# --- 4. 데이터 및 캐시 로드 ---
CACHE_FILE = "data/generated_cache.json"

@st.cache_data
def load_json_data(file_path):
    """지정된 경로의 JSON 파일을 로드하는 함수"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"'{file_path}' 파일을 찾을 수 없습니다. 'data' 폴더에 파일이 있는지 확인해주세요.")
        return None
    except json.JSONDecodeError:
        st.error(f"'{file_path}' 파일의 형식이 올바르지 않습니다.")
        return None

# 각 데이터 파일을 로드합니다. 파일명에서 특수문자는 제거했습니다.
grade_data_1_2 = load_json_data('data/1-2학년군_성취수준.json')
grade_data_3_4 = load_json_data('data/3-4학년군_성취수준.json')
grade_data_5_6 = load_json_data('data/5-6학년군_성취수준.json')
guidelines_data = load_json_data('data/교과평어_기재요령_정리본.json')

def load_cache():
    """API 생성 결과가 저장된 캐시 파일을 로드하는 함수"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache_data):
    """캐시 데이터를 파일에 저장하는 함수"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

# --- 5. 핵심 기능 함수 ---
def get_subjects_for_grade(grade):
    """선택된 학년에 맞는 교과목 리스트를 반환하는 함수"""
    if grade in ["1학년", "2학년"]:
        return ["국어", "수학", "바른 생활", "슬기로운 생활", "즐거운 생활"]
    elif grade in ["3학년", "4학년"]:
        return ["국어", "사회", "도덕", "수학", "과학", "체육", "음악", "미술", "영어"]
    elif grade in ["5학년", "6학년"]:
        return ["국어", "사회", "도덕", "수학", "과학", "실과", "체육", "음악", "미술", "영어"]
    return []

def get_data_for_grade(grade):
    """선택된 학년에 맞는 성취수준 데이터셋을 반환하는 함수"""
    if grade in ["1학년", "2학년"]: return grade_data_1_2
    if grade in ["3학년", "4학년"]: return grade_data_3_4
    if grade in ["5학년", "6학년"]: return grade_data_5_6
    return None

def get_subject_block(data, subject):
    """전체 텍스트에서 특정 과목에 해당하는 텍스트 블록을 추출하는 함수"""
    if not isinstance(data, dict) or 'content' not in data:
        return None
    content_string = data['content']
    subject_pattern = re.compile(r'\n\d+\s+' + re.escape(subject) + r'\n')
    match = subject_pattern.search(content_string)
    if not match:
        return None
    start_index = match.end()
    next_subject_pattern = re.compile(r'\n\d+\s+\w+\n')
    next_match = next_subject_pattern.search(content_string, start_index)
    end_index = next_match.start() if next_match else len(content_string)
    return content_string[start_index:end_index]

def get_domains(subject_block):
    """과목 텍스트 블록에서 중복 없는 영역(domain) 목록을 추출하는 함수"""
    if not subject_block:
        return []
    domain_pattern = re.compile(r'\(\d+\)\s+([^\n]+)')
    domains = domain_pattern.findall(subject_block)
    return list(dict.fromkeys([d.strip() for d in domains]))

def get_achievement_standards(subject_block, domain):
    """선택된 영역(domain)에 해당하는 성취기준 리스트를 파싱하는 함수"""
    try:
        domain_pattern = re.compile(r'\(\d+\)\s+' + re.escape(domain) + r'\n(.*?)(?=\n\(\d+\)\s+|\Z)', re.DOTALL)
        domain_match = domain_pattern.search(subject_block)
        if not domain_match:
            return []
        
        domain_block = domain_match.group(1)

        standards_list = []
        pattern = re.compile(r'(\[.*?\][^\n]+)\n+A\n(.*?)\n+B\n(.*?)\n+C\n(.*?)(?=\n\[|\Z)', re.DOTALL)
        
        for match in pattern.finditer(domain_block):
            standard, a_desc, b_desc, c_desc = match.groups()
            standards_list.append({
                "성취기준": standard.strip(),
                "성취기준별 성취수준": {
                    "A": a_desc.strip(),
                    "B": b_desc.strip(),
                    "C": c_desc.strip()
                }
            })
        return standards_list

    except Exception as e:
        st.error(f"데이터 파싱 중 오류가 발생했습니다: {e}")
        return []

def generate_prompt(guidelines, standard_info, num_high, num_mid, num_low):
    """Gemini API에 보낼 프롬프트를 생성하는 함수 (품질 개선을 위해 대폭 수정)"""
    examples = guidelines.get('3. 작성 예시', {})
    summary = guidelines.get('5. 정리', '학생의 학습 과정과 변화를 기록하는 ‘관찰 기반 서술형 기록’입니다.')

    example_text = ""
    for subject, example in examples.items():
        example_text += f"- {subject} 예시: \"{example}\"\n"

    prompt = f"""
    당신은 20년 경력의 대한민국 초등학교 담임교사입니다. 학생의 교과학습발달상황(세부능력 및 특기사항)을 '{summary}' 원칙에 따라 작성해야 합니다.

    **[매우 중요한 작성 원칙]**
    1. **문장 형식 (가장 중요):** 모든 문장은 학생의 이름 없이, 학생의 행동을 서술하는 형식으로 끝나야 합니다. 문장의 어미는 반드시 '~함.', '~임.', '~음.', '~관찰됨.', '~보여줌.' 과 같은 서술형으로 끝나야 합니다.
    2. **학생 주어 제거:** 절대로 'OO 학생은' 또는 'OO는'과 같은 학생 주어를 포함하지 마세요. 순수한 서술부만 생성해야 합니다.
    3. **객관성과 구체성:** '잘함', '우수함' 같은 주관적인 판단 대신, 학생이 무엇을 어떻게 했는지 관찰된 사실을 기반으로 서술하세요.
    4. **과정과 성장:** 결과뿐만 아니라 학생의 학습 과정, 태도의 변화, 노력, 성장의 모습이 드러나도록 작성하세요.
    5. **성취기준 연계:** 제시된 [성취기준 정보]와 밀접하게 관련된 내용으로 작성하세요.

    **[좋은 작성 예시]**
    {example_text}

    **[성취기준 정보]**
    - 성취기준: {standard_info.get('성취기준', '정보 없음')}
    - 성취수준(상): {standard_info.get('성취기준별 성취수준', {}).get('A', '정보 없음')}
    - 성취수준(중): {standard_info.get('성취기준별 성취수준', {}).get('B', '정보 없음')}
    - 성취수준(하): {standard_info.get('성취기준별 성취수준', {}).get('C', '정보 없음')}

    **[생성 요청]**
    - '상' 수준 문장: {num_high}개
    - '중' 수준 문장: {num_mid}개
    - '하' 수준 문장: {num_low}개
    
    이제, 위의 모든 지침과 예시를 철저히 따라서, 요청된 개수만큼 교과 평어 문장을 JSON 형식으로 생성해주세요.
    {{
      "상": ["문장 1", ...],
      "중": ["문장 1", ...],
      "하": ["문장 1", ...]
    }}
    """
    return prompt

def get_feedback_sentences(standard_key, standard_info, num_high, num_mid, num_low):
    """캐시를 확인하고, 없으면 Gemini API를 호출하여 평어 문장을 가져오는 함수"""
    cache_key = f"{standard_key}_{num_high}_{num_mid}_{num_low}"
    cache = load_cache()
    
    if cache_key in cache:
        st.info("✅ 저장된 생성 결과를 불러왔습니다.")
        return cache[cache_key]
    else:
        with st.spinner("✨ Gemini API가 새로운 문장을 생성하고 있습니다..."):
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = generate_prompt(guidelines_data, standard_info, num_high, num_mid, num_low)
                response = model.generate_content(prompt)
                
                cleaned_response = re.search(r'\{.*\}', response.text, re.DOTALL)
                if cleaned_response:
                    new_sentences = json.loads(cleaned_response.group(0))
                else:
                    st.error("API로부터 유효한 JSON 형식의 응답을 받지 못했습니다.")
                    return None

                cache[cache_key] = new_sentences
                save_cache(cache)
                return new_sentences
            except Exception as e:
                st.error(f"API 호출 중 오류가 발생했습니다: {e}")
                return None

def reset_generation_state():
    """사이드바 선택 변경 시 생성 시작 상태를 초기화하는 함수"""
    st.session_state.start_generation = False

# --- 6. UI 렌더링 ---
st.title("✍️ AI 교과평어 생성 도우미")
st.markdown("2022 개정 교육과정에 기반하여, 학생의 성취수준에 맞는 교과평어 문장을 생성하고 조합할 수 있습니다.")

# 사이드바 UI 구성
with st.sidebar:
    st.header("⏬ 조건 선택")
    selected_grade = st.selectbox("학년", ["1학년", "2학년", "3학년", "4학년", "5학년", "6학년"], key="grade_select", on_change=reset_generation_state)
    
    available_subjects = get_subjects_for_grade(selected_grade)
    selected_subject = st.selectbox("교과목", available_subjects, key="subject_select", on_change=reset_generation_state)
    
    st.divider()
    st.header("🔢 생성 개수 설정")
    num_high = st.number_input("'상' 수준 문장 개수", min_value=1, max_value=25, value=2)
    num_mid = st.number_input("'중' 수준 문장 개수", min_value=1, max_value=25, value=2)
    num_low = st.number_input("'하' 수준 문장 개수", min_value=1, max_value=25, value=2)

    st.divider()
    if st.button("🚀 교과평어 생성 시작", use_container_width=True):
        st.session_state.start_generation = True
        st.rerun()

# 메인 화면 UI 구성
if st.session_state.start_generation:
    if all([grade_data_1_2, grade_data_3_4, grade_data_5_6, guidelines_data]):
        grade_data = get_data_for_grade(selected_grade)
        if grade_data:
            subject_block_text = get_subject_block(grade_data, selected_subject)
            domains = get_domains(subject_block_text)
            
            if not domains:
                st.warning("선택한 과목의 영역을 찾을 수 없습니다.")
            else:
                selected_domain = st.selectbox("영역 선택", domains, key=f"{selected_grade}_{selected_subject}_domain")
                
                st.header(f"📖 {selected_grade} - {selected_subject} ({selected_domain})")
                
                standards = get_achievement_standards(subject_block_text, selected_domain)
                
                if not standards:
                    st.warning("선택한 영역에 해당하는 성취기준을 찾을 수 없습니다.")
                else:
                    standard_texts = [s.get('성취기준', '내용 없음') for s in standards]
                    selected_standard_text = st.selectbox("성취기준 선택", standard_texts, key="standard_select")

                    selected_standard_info = next((s for s in standards if s.get('성취기준') == selected_standard_text), None)

                    if selected_standard_info:
                        standard_code_match = re.search(r'\[(.*?)\]', selected_standard_text)
                        standard_code = standard_code_match.group(1) if standard_code_match else "selected_std"
                        
                        standard_key = f"{selected_grade}_{selected_subject}_{standard_code}"

                        st.markdown("---")
                        
                        sentences = get_feedback_sentences(standard_key, selected_standard_info, num_high, num_mid, num_low)
                        
                        if sentences:
                            levels = ["상", "중", "하"]
                            for level in levels:
                                st.markdown(f"**{level} (성취수준 {'ABC'[levels.index(level)]})**")
                                for sent_idx, sentence in enumerate(sentences.get(level, [])):
                                    button_key = f"{standard_key}_{level}_{sent_idx}_{num_high}_{num_mid}_{num_low}"
                                    if st.button(sentence, key=button_key, use_container_width=True):
                                        if not sentence.endswith('.'):
                                            sentence += '.'
                                        st.session_state.final_sentences.append(sentence)
                                        st.rerun()
                        else:
                            st.warning("문장을 생성하지 못했습니다.")
else:
    st.info("⬅️ 왼쪽 사이드바에서 학년, 과목, 생성 개수를 선택한 후 '교과평어 생성 시작' 버튼을 눌러주세요.")

# 최종 결과창 UI (항상 표시)
st.divider()
st.header("📋 학기말 종합의견 (조합 결과)")

combined_text = " ".join(st.session_state.final_sentences)
edited_text = st.text_area(
    "결과 확인 및 편집",
    value=combined_text,
    height=300,
    placeholder="생성된 문장을 클릭하면 이곳에 추가됩니다. 자유롭게 편집할 수 있습니다."
)

col1, col2, _ = st.columns([1, 1, 4])
with col1:
    st.button("📋 내용 복사", help="텍스트 영역의 내용을 직접 복사(Ctrl+C)하세요.")
with col2:
    if st.button("🔄 모두 지우기"):
        st.session_state.final_sentences = []
        st.session_state.start_generation = False
        st.rerun()

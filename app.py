import streamlit as st
from openai import OpenAI
import os
from dotenv import load_dotenv
import time
import json
from datetime import datetime
from textblob import TextBlob
import sqlite3
import pandas as pd

# Load environment variables
load_dotenv()

# Set up OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Use the pre-trained assistant ID
ASSISTANT_ID = "asst_8uJ0vuy8Py0fJWCvbcH5NuB9"

# Define situation type mapping
SITUATION_TYPES = {
    "学习相关（如图书馆使用、与教授沟通等）": "学习相关",
    "文化适应（如理解美国人的社交习惯）": "文化适应",
    "生活问题（如住宿、交通、饮食等）": "生活问题",
    "其他": "其他"
}

# Database setup
def init_db():
    conn = sqlite3.connect('cultural_navigator.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS anonymous_posts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  content TEXT NOT NULL,
                  category TEXT,
                  sentiment_score REAL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS emotional_states
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_session TEXT,
                  emotion TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Initialize database
init_db()

def analyze_emotion(text):
    """Analyze emotion in text using TextBlob"""
    analysis = TextBlob(text)
    return {
        'polarity': analysis.sentiment.polarity,
        'subjectivity': analysis.sentiment.subjectivity
    }

def save_anonymous_post(content, category):
    """Save anonymous post to database"""
    sentiment = analyze_emotion(content)
    conn = sqlite3.connect('cultural_navigator.db')
    c = conn.cursor()
    c.execute('''INSERT INTO anonymous_posts (content, category, sentiment_score)
                 VALUES (?, ?, ?)''', (content, category, sentiment['polarity']))
    conn.commit()
    conn.close()

def get_anonymous_posts():
    """Retrieve anonymous posts from database"""
    conn = sqlite3.connect('cultural_navigator.db')
    posts = pd.read_sql_query("SELECT * FROM anonymous_posts ORDER BY timestamp DESC", conn)
    conn.close()
    return posts

def get_or_create_thread():
    if "thread_id" not in st.session_state:
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
    return st.session_state.thread_id

def check_active_runs(thread_id):
    """Check if there are any active runs for the thread"""
    try:
        runs = client.beta.threads.runs.list(thread_id=thread_id)
        for run in runs.data:
            if run.status in ['queued', 'in_progress', 'requires_action']:
                return True
        return False
    except Exception:
        return False

def generate_response(prompt, query_type, context=None):
    try:
        thread_id = get_or_create_thread()
        
        # Check for active runs
        if check_active_runs(thread_id):
            return "请稍等片刻，我正在处理您的上一个问题..."

        # Enhance prompt based on query type and context
        if query_type == "cultural_advice":
            full_prompt = f"作为文化顾问，请针对以下情况提供详细的建议和解释：{prompt}\n考虑用户背景：{context}"
        elif query_type == "emotion_support":
            emotion_data = analyze_emotion(prompt)
            full_prompt = f"考虑到用户情绪状态（情感极性：{emotion_data['polarity']}），请提供温和的支持和建议：{prompt}"
        elif query_type == "anonymous_sharing":
            full_prompt = f"对于这个匿名分享：{prompt}\n请提供理解和支持性的回应，同时考虑文化敏感性"
        else:
            full_prompt = prompt

        try:
            # Add message to thread
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=full_prompt
            )
        except Exception as e:
            if "while a run" in str(e) and "is active" in str(e):
                return "请稍等片刻，我正在处理您的上一个问题..."
            raise e

        # Run assistant with the pre-trained assistant ID
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        # Wait for response
        while True:
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            if run_status.status == 'completed':
                break
            elif run_status.status == 'failed':
                return "对话生成失败，请重试。"
            time.sleep(1)

        # Get assistant's response
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        assistant_message = next((m for m in messages if m.role == 'assistant'), None)
        
        if assistant_message:
            return assistant_message.content[0].text.value
        else:
            return "助手没有提供回复。"

    except Exception as e:
        if "while a run" in str(e) and "is active" in str(e):
            return "请稍等片刻，我正在处理您的上一个问题..."
        return f"发生错误：{str(e)}"

def display_messages(messages, container, message_type):
    """Display messages with delete buttons"""
    for idx, message in enumerate(messages):
        col1, col2 = container.columns([0.9, 0.1])
        with col1:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        with col2:
            if st.button("删除", key=f"delete_{message_type}_{idx}"):
                del messages[idx]
                st.experimental_rerun()

def main():
    st.set_page_config(page_title="文化导航助手", layout="wide")

    # Initialize session states for different message types
    if "cultural_messages" not in st.session_state:
        st.session_state.cultural_messages = []
    if "emotional_messages" not in st.session_state:
        st.session_state.emotional_messages = []
    if "current_status" not in st.session_state:
        st.session_state.current_status = ""
    if "situation_type" not in st.session_state:
        st.session_state.situation_type = "学习相关"
    if "emotional_state" not in st.session_state:
        st.session_state.emotional_state = "一般"

    # Sidebar for navigation
    st.sidebar.title("功能导航")
    page = st.sidebar.radio(
        "选择功能：",
        ["文化咨询", "情感支持", "匿名树洞", "历史记录"]
    )

    if page == "文化咨询":
        st.title("文化咨询")
        
        # Welcome message and explanation
        st.markdown("""
        ### 亲爱的朋友！🌟 
        
        是不是感觉新环境有点让人手足无措？别担心，我们都经历过这个阶段。来来来，让我们一起聊聊你遇到的具体问题吧！
        
        请填写下面的信息，帮助我们更好地了解你的情况，提供更有针对性的建议。
        """)

        # User information form
        with st.form("user_info_form", clear_on_submit=False):
            current_status = st.text_area(
                "当前状态描述",
                value=st.session_state.current_status,
                placeholder="请简要描述你目前的情况，比如：刚来美国一个月，正在适应新的学习环境..."
            )
            
            # 使用带示例的选项显示，但在后端使用简化的值
            situation_type_display = st.selectbox(
                "情景类型",
                list(SITUATION_TYPES.keys())
            )
            
            # 获取实际的情景类型值（不包含示例）
            situation_type = SITUATION_TYPES[situation_type_display]
            
            # 如果选择"其他"，显示文本输入框
            other_situation_text = ""
            if situation_type == "其他":
                other_situation_text = st.text_input("请描述您的具体情景：")
            
            emotional_state = st.select_slider(
                "当前情绪状态",
                options=["非常困扰", "有点焦虑", "一般", "还好", "很乐观"],
                value=st.session_state.emotional_state
            )

            submitted = st.form_submit_button("保存基本信息")
            
            if submitted:
                st.session_state.current_status = current_status
                st.session_state.emotional_state = emotional_state
                
                # 处理情景类型
                if situation_type == "其他" and other_situation_text:
                    st.session_state.situation_type = f"其他：{other_situation_text}"
                else:
                    st.session_state.situation_type = situation_type
                
                st.success("基本信息已保存！")

        # Create a container for chat messages
        chat_container = st.container()

        # Display cultural consultation messages
        display_messages(st.session_state.cultural_messages, chat_container, "cultural")

        # Question input
        user_input = st.chat_input("请详细描述你最关心的具体问题或疑虑...")

        if user_input:
            # Prepare context
            context = f"""
            情景类型：{st.session_state.situation_type}
            当前状态：{st.session_state.current_status}
            情绪状态：{st.session_state.emotional_state}
            """
            
            response = generate_response(user_input, "cultural_advice", context)
            
            # Only append messages if it's not a waiting message
            if not response.startswith("请稍等片刻"):
                # Save to cultural messages history
                st.session_state.cultural_messages.append({"role": "user", "content": user_input})
                st.session_state.cultural_messages.append({"role": "assistant", "content": response})
                st.experimental_rerun()
            else:
                # Show waiting message without adding to history
                st.info(response)

    elif page == "情感支持":
        st.title("情感支持")
        
        # Welcome message and explanation for emotional support
        st.markdown("""
        ### 温暖的倾听空间 💝
        
        每个人都会有情绪起伏的时候，这里是你的安全港湾。
        无论是学业压力、思乡之情，还是对未来的迷茫，都可以在这里倾诉。
        
        我们会认真倾听你的每一个感受，给予温暖的支持和建议。
        请随意分享你的心情，让我们一起面对。
        """)
        
        # Create a container for chat messages
        chat_container = st.container()

        # Display emotional support messages
        display_messages(st.session_state.emotional_messages, chat_container, "emotional")
        
        user_input = st.chat_input("分享您的感受...")
        
        if user_input:
            response = generate_response(user_input, "emotion_support")
            
            # Only append messages if it's not a waiting message
            if not response.startswith("请稍等片刻"):
                # Save to emotional messages history
                st.session_state.emotional_messages.append({"role": "user", "content": user_input})
                st.session_state.emotional_messages.append({"role": "assistant", "content": response})
                st.experimental_rerun()
            else:
                # Show waiting message without adding to history
                st.info(response)

    elif page == "匿名树洞":
        st.title("匿名树洞")
        
        # Welcome message and explanation for anonymous sharing
        st.markdown("""
        ### 匿名分享空间 🌳
        
        这里是你的秘密花园，可以自由地分享任何想法和经历。
        
        - 完全匿名：所有分享都是匿名的，请放心表达
        - 互相支持：看到他人的分享，也可以提供你的建议
        - 共同成长：在这里，我们互相理解，共同进步
        
        选择一个分类，开始你的分享吧！
        """)
        
        tab1, tab2 = st.tabs(["发布新帖", "查看分享"])
        
        with tab1:
            post_category = st.selectbox(
                "选择分类：",
                ["学业压力", "文化适应", "人际关系", "其他"]
            )
            post_content = st.text_area("分享您的故事...")
            if st.button("发布"):
                save_anonymous_post(post_content, post_category)
                st.success("发布成功！")
        
        with tab2:
            posts = get_anonymous_posts()
            for _, post in posts.iterrows():
                with st.expander(f"{post['category']} - {post['timestamp'][:16]}"):
                    st.write(post['content'])
                    if st.button("提供支持", key=post['id']):
                        response = generate_response(post['content'], "anonymous_sharing")
                        if not response.startswith("请稍等片刻"):
                            st.write("AI支持回应：", response)
                        else:
                            st.info(response)

    elif page == "历史记录":
        st.title("对话历史")
        
        # Explanation for history page
        st.markdown("""
        ### 你的成长轨迹 📝
        
        这里记录了你之前的所有对话和交流。
        回顾过去的对话可以帮助你看到自己的进步和成长。
        """)
        
        tab1, tab2 = st.tabs(["文化咨询记录", "情感支持记录"])
        
        with tab1:
            cultural_container = st.container()
            display_messages(st.session_state.cultural_messages, cultural_container, "cultural_history")
            
        with tab2:
            emotional_container = st.container()
            display_messages(st.session_state.emotional_messages, emotional_container, "emotional_history")

    # Clear chat buttons in sidebar
    if st.sidebar.button("清除文化咨询记录"):
        st.session_state.cultural_messages = []
        if "thread_id" in st.session_state:
            del st.session_state.thread_id
        st.experimental_rerun()
        
    if st.sidebar.button("清除情感支持记录"):
        st.session_state.emotional_messages = []
        if "thread_id" in st.session_state:
            del st.session_state.thread_id
        st.experimental_rerun()

if __name__ == "__main__":
    main()

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

# Define situation type mapping
SITUATION_TYPES = {
    "学习相关（如图书馆使用、与教授沟通等）": "学习相关",
    "文化适应（如理解美国人的社交习惯）": "文化适应",
    "生活问题（如住宿、交通、饮食等）": "生活问题",
    "其他": "其他"
}

# Optimized callback functions with batched updates
def update_situation_state():
    # Only update if there's a change in situation type
    new_situation_type = SITUATION_TYPES[st.session_state.situation_input]
    if new_situation_type != st.session_state.get('situation_type', ''):
        st.session_state.situation_type = new_situation_type
        # Reset other situation text when switching away from "其他"
        if new_situation_type != "其他":
            st.session_state.other_situation_text = ""
            st.session_state.other_situation_enabled = False
        else:
            st.session_state.other_situation_enabled = True

def update_other_situation():
    if st.session_state.other_situation_text and st.session_state.situation_type == "其他":
        st.session_state.situation_type = f"其他：{st.session_state.other_situation_text}"

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

def get_chat_messages(message_type):
    """Get chat messages from session state"""
    if message_type not in st.session_state:
        st.session_state[message_type] = []
    return st.session_state[message_type]

def generate_response(prompt, query_type, context=None):
    """Generate response using OpenAI API"""
    try:
        messages = []
        
        # Add system message based on query type
        if query_type == "cultural_advice":
            system_message = """你是一位经验丰富的文化顾问，专门帮助国际学生适应新的文化环境。
            你需要：
            1. 提供具体、实用的建议
            2. 解释文化差异背后的原因
            3. 分享相关的文化习俗和礼仪
            4. 给出实际的例子和情境
            请基于用户的具体情况提供个性化的建议。"""
            
            # Add context to the conversation
            if context:
                messages.append({"role": "system", "content": system_message})
                messages.append({"role": "user", "content": f"用户背景信息：{context}"})
        
        elif query_type == "emotion_support":
            emotion_data = analyze_emotion(prompt)
            system_message = f"""你是一位富有同理心的心理支持顾问。
            用户当前的情感状态显示情感极性为{emotion_data['polarity']}。
            请：
            1. 表达理解和认同
            2. 提供情感支持
            3. 给出实用的建议
            4. 鼓励积极的态度
            注意使用温和、支持性的语言。"""
            messages.append({"role": "system", "content": system_message})
        
        elif query_type == "anonymous_sharing":
            system_message = """你是一位理解和支持的倾听者。
            对于匿名分享：
            1. 表示理解和同理
            2. 分享类似经历（如果适用）
            3. 提供建设性的建议
            4. 鼓励继续分享
            请保持文化敏感性。"""
            messages.append({"role": "system", "content": system_message})

        # Add the user's prompt
        messages.append({"role": "user", "content": prompt})

        # Get chat history
        chat_history = get_chat_messages(f"{query_type}_messages")
        
        # Add recent chat history (last 5 exchanges) to maintain context
        if chat_history:
            recent_history = chat_history[-10:]  # Get last 5 exchanges (10 messages)
            for msg in recent_history:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Generate response using chat completion
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )

        return response.choices[0].message.content

    except Exception as e:
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

    # Add custom CSS to align the button to the right
    st.markdown("""
        <style>
        div.stButton > button {
            float: right;
        }
        </style>
    """, unsafe_allow_html=True)

    # Initialize session states
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
    if "other_situation_enabled" not in st.session_state:
        st.session_state.other_situation_enabled = False
    if "other_situation_text" not in st.session_state:
        st.session_state.other_situation_text = ""

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

        # User information inputs with optimized updates
        current_status = st.text_area(
            "当前状态描述",
            value=st.session_state.current_status,
            placeholder="请简要描述你目前的情况，比如：刚来美国一个月，正在适应新的学习环境...",
            key="status_input"
        )
        if current_status != st.session_state.current_status:
            st.session_state.current_status = current_status
        
        # Create columns for situation type selection
        col1, col2 = st.columns([0.7, 0.3])
        
        with col1:
            st.selectbox(
                "情景类型",
                list(SITUATION_TYPES.keys()),
                key="situation_input",
                on_change=update_situation_state
            )
        
        with col2:
            other_situation = st.text_input(
                "其他情景",
                value=st.session_state.other_situation_text,
                placeholder="请描述您的具体情景",
                disabled=not st.session_state.other_situation_enabled,
                key="other_situation_text",
                on_change=update_other_situation
            )
        
        emotional_state = st.select_slider(
            "当前情绪状态",
            options=["非常困扰", "有点焦虑", "一般", "还好", "很乐观"],
            value=st.session_state.emotional_state
        )
        if emotional_state != st.session_state.emotional_state:
            st.session_state.emotional_state = emotional_state

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
            
            with st.spinner('正在认真倾听你的心事...'):
                # Generate response
                response = generate_response(user_input, "cultural_advice", context)
                
                # Save both messages after response is generated
                st.session_state.cultural_messages.append({"role": "user", "content": user_input})
                st.session_state.cultural_messages.append({"role": "assistant", "content": response})
                st.experimental_rerun()

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
            with st.spinner('正在认真倾听你的心事...'):
                # Generate response
                response = generate_response(user_input, "emotion_support")
                
                # Save both messages after response is generated
                st.session_state.emotional_messages.append({"role": "user", "content": user_input})
                st.session_state.emotional_messages.append({"role": "assistant", "content": response})
                st.experimental_rerun()

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
                with st.spinner('正在发布中...'):
                    save_anonymous_post(post_content, post_category)
                st.success("发布成功！")
        
        with tab2:
            posts = get_anonymous_posts()
            for _, post in posts.iterrows():
                with st.expander(f"{post['category']} - {post['timestamp'][:16]}"):
                    st.write(post['content'])
                    if st.button("提供支持", key=post['id']):
                        with st.spinner('正在生成回应...'):
                            response = generate_response(post['content'], "anonymous_sharing")
                            st.write("AI支持回应：", response)

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
        st.experimental_rerun()
        
    if st.sidebar.button("清除情感支持记录"):
        st.session_state.emotional_messages = []
        st.experimental_rerun()

if __name__ == "__main__":
    main()

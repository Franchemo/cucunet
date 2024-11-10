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
import plotly.express as px
import plotly.graph_objects as go

# Load environment variables
load_dotenv()

# Set up OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Define mood colors and scores for anonymous posts
MOOD_COLORS = {
    "非常开心 😊": {"color": "#FFD700", "score": 100},  # Gold
    "心情不错 🙂": {"color": "#98FB98", "score": 75},   # Pale Green
    "一般般 😐": {"color": "#87CEEB", "score": 50},     # Sky Blue
    "有点低落 😔": {"color": "#DDA0DD", "score": 25},   # Plum
    "很难过 😢": {"color": "#CD5C5C", "score": 0}      # Indian Red
}

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
    
    # Create anonymous posts table with new fields
    c.execute('''CREATE TABLE IF NOT EXISTS anonymous_posts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  content TEXT NOT NULL,
                  category TEXT,
                  mood TEXT,
                  mood_color TEXT,
                  post_date DATE,
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

def save_anonymous_post(content, category, mood=None, mood_color=None, post_date=None):
    """Save anonymous post to database with mood and date"""
    sentiment = analyze_emotion(content)
    conn = sqlite3.connect('cultural_navigator.db')
    c = conn.cursor()
    
    # Get mood score if mood is provided
    mood_score = MOOD_COLORS[mood]["score"] if mood else 50
    
    c.execute('''INSERT INTO anonymous_posts 
                 (content, category, mood, mood_color, post_date, sentiment_score)
                 VALUES (?, ?, ?, ?, ?, ?)''', 
              (content, category, mood, MOOD_COLORS[mood]["color"] if mood else None, post_date, mood_score))
    conn.commit()
    conn.close()

def get_anonymous_posts():
    """Retrieve anonymous posts from database"""
    conn = sqlite3.connect('cultural_navigator.db')
    posts = pd.read_sql_query(
        "SELECT * FROM anonymous_posts ORDER BY timestamp DESC", 
        conn,
        parse_dates=['post_date']
    )
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

def create_mood_calendar(posts):
    """Create a calendar visualization of moods"""
    if len(posts) == 0:
        return None
    
    # Create calendar data
    calendar_data = posts.copy()
    calendar_data['post_date'] = pd.to_datetime(calendar_data['post_date'])
    
    # Get the current month's data
    current_month = calendar_data['post_date'].dt.to_period('M').iloc[0]
    month_data = calendar_data[calendar_data['post_date'].dt.to_period('M') == current_month]
    
    # Create calendar grid using plotly
    fig = go.Figure()
    
    # Get the number of days in the month
    year = current_month.year
    month = current_month.month
    num_days = pd.Period(current_month).days_in_month
    
    # Create a date range for the entire month
    date_range = pd.date_range(start=f"{year}-{month:02d}-01", 
                             end=f"{year}-{month:02d}-{num_days}")
    
    # Calculate the week number for each day
    weeks = [d.isocalendar()[1] for d in date_range]
    min_week = min(weeks)
    
    # Create grid of all days
    for date in date_range:
        day = date.day
        week = date.isocalendar()[1] - min_week
        
        # Check if we have mood data for this day
        day_data = month_data[month_data['post_date'].dt.date == date.date()]
        
        if not day_data.empty:
            # Use the mood color from the data
            color = day_data.iloc[0]['mood_color']
            hover_text = f"日期: {date.strftime('%Y-%m-%d')}<br>心情: {day_data.iloc[0]['mood']}<br>分类: {day_data.iloc[0]['category']}<br>内容: {day_data.iloc[0]['content'][:50]}..."
        else:
            # Use a neutral color for days without data
            color = '#EAEAEA'
            hover_text = f"日期: {date.strftime('%Y-%m-%d')}<br>没有记录"
        
        # Add square for the day
        fig.add_trace(go.Scatter(
            x=[week],
            y=[day],
            mode='markers',
            marker=dict(
                color=color,
                size=30,
                symbol='square',
                line=dict(color='#FFFFFF', width=1)
            ),
            text=hover_text,
            hoverinfo='text',
            showlegend=False
        ))
    
    # Update layout
    fig.update_layout(
        title=f"心情日历 - {year}年{month}月",
        xaxis_title="周",
        yaxis_title="日",
        height=500,
        margin=dict(l=40, r=40, t=60, b=40),
        plot_bgcolor='white',
        xaxis=dict(
            tickmode='array',
            ticktext=['第1周', '第2周', '第3周', '第4周', '第5周', '第6周'],
            tickvals=list(range(6)),
            gridcolor='#EAEAEA',
            showgrid=True
        ),
        yaxis=dict(
            tickmode='array',
            ticktext=[str(i) for i in range(1, 32)],
            tickvals=list(range(1, 32)),
            gridcolor='#EAEAEA',
            showgrid=True,
            autorange='reversed'  # Reverse y-axis to show days from top to bottom
        )
    )
    
    return fig

def create_mood_tracking_graph(posts):
    """Create a line graph showing mood trends over time"""
    if len(posts) == 0:
        return None
    
    # Create mood tracking data
    mood_data = posts.copy()
    mood_data['post_date'] = pd.to_datetime(mood_data['post_date'])
    
    # Sort by date
    mood_data = mood_data.sort_values('post_date')
    
    # Create line graph
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=mood_data['post_date'],
        y=mood_data['sentiment_score'],
        mode='lines+markers',
        line=dict(color='#6495ED', width=2),
        marker=dict(
            color=mood_data['mood_color'],
            size=12,
            line=dict(color='white', width=1)
        ),
        text=mood_data['mood'],
        hovertemplate="日期: %{x}<br>心情: %{text}<br>心情指数: %{y}<extra></extra>"
    ))
    
    # Update layout
    fig.update_layout(
        title="心情变化趋势",
        xaxis_title="日期",
        yaxis_title="心情指数",
        yaxis=dict(
            range=[0, 100],
            tickmode='array',
            ticktext=['很难过', '有点低落', '一般', '心情不错', '非常开心'],
            tickvals=[0, 25, 50, 75, 100]
        ),
        height=300,
        margin=dict(l=40, r=40, t=60, b=40),
        plot_bgcolor='white',
        xaxis=dict(gridcolor='#EAEAEA'),
        yaxis_gridcolor='#EAEAEA'
    )
    
    return fig

def main():
    st.set_page_config(page_title="文化导航助手", layout="wide")

    # Add custom CSS
    st.markdown("""
        <style>
        div.stButton > button {
            float: right;
        }
        .mood-tracker {
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 10px;
            margin: 20px 0;
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

    # Sidebar navigation
    st.sidebar.title("功能导航")
    page = st.sidebar.radio(
        "选择功能：",
        ["文化适应加油站⛽️", "暖心聊聊天💕", "匿名树洞🌳", "我的故事"]
    )

    if page == "文化适应加油站⛽️":
        st.title("文化适应加油站⛽️")
        
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
                key="situation_input"
            )
        
        with col2:
            other_situation = st.text_input(
                "其他情景",
                value=st.session_state.other_situation_text,
                placeholder="请描述您的具体情景",
                disabled=not st.session_state.other_situation_enabled,
                key="other_situation_text"
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
        for idx, message in enumerate(st.session_state.cultural_messages):
            col1, col2 = chat_container.columns([0.9, 0.1])
            with col1:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            with col2:
                if st.button("删除", key=f"delete_cultural_{idx}"):
                    del st.session_state.cultural_messages[idx]
                    st.experimental_rerun()

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

    elif page == "暖心聊聊天💕":
        st.title("暖心聊聊天💕")
        
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
        for idx, message in enumerate(st.session_state.emotional_messages):
            col1, col2 = chat_container.columns([0.9, 0.1])
            with col1:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            with col2:
                if st.button("删除", key=f"delete_emotional_{idx}"):
                    del st.session_state.emotional_messages[idx]
                    st.experimental_rerun()
        
        user_input = st.chat_input("分享您的感受...")
        
        if user_input:
            with st.spinner('正在认真倾听你的心事...'):
                # Generate response
                response = generate_response(user_input, "emotion_support")
                
                # Save both messages after response is generated
                st.session_state.emotional_messages.append({"role": "user", "content": user_input})
                st.session_state.emotional_messages.append({"role": "assistant", "content": response})
                st.experimental_rerun()

    elif page == "匿名树洞🌳":
        st.title("匿名树洞🌳")
        
        st.markdown("""
        ### 匿名分享空间 🌳
        
        这里是你的秘密花园，可以自由地分享任何想法和经历。记录你的心情，追踪你的情绪变化。
        
        - 完全匿名：所有分享都是匿名的，请放心表达
        - 心情记录：选择代表你当前心情的颜色
        - 可视化追踪：通过日历和图表直观地看到你的情绪变化
        """)
        
        tab1, tab2, tab3 = st.tabs(["发布新帖", "查看分享", "心情追踪"])
        
        with tab1:
            # Post creation form
            post_category = st.selectbox(
                "选择分类：",
                ["学业压力", "文化适应", "人际关系", "其他"]
            )
            
            # Mood selection
            selected_mood = st.select_slider(
                "当前心情：",
                options=list(MOOD_COLORS.keys()),
                value="一般般 😐"
            )
            
            # Show selected color
            st.markdown(f"""
                <div style="width: 30px; height: 30px; background-color: {MOOD_COLORS[selected_mood]['color']}; 
                border-radius: 5px; margin: 10px 0;"></div>
            """, unsafe_allow_html=True)
            
            # Date selection
            post_date = st.date_input(
                "选择日期：",
                value=datetime.now()
            )
            
            # Content input
            post_content = st.text_area("分享您的故事...")
            
            if st.button("发布"):
                if post_content:
                    with st.spinner('正在发布中...'):
                        save_anonymous_post(
                            post_content, 
                            post_category,
                            selected_mood,
                            MOOD_COLORS[selected_mood]['color'],
                            post_date
                        )
                    st.success("发布成功！")
                else:
                    st.warning("请输入内容后再发布")
        
        with tab2:
            # Get all posts
            posts = get_anonymous_posts()
            
            if not posts.empty:
                # Display posts
                st.markdown("### 历史分享")
                for _, post in posts.iterrows():
                    with st.expander(f"{post['category']} - {post['timestamp'][:16]}"):
                        # Show mood indicator if mood is available
                        if post['mood'] and post['mood_color']:
                            st.markdown(f"""
                                <div style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <div style="width: 20px; height: 20px; background-color: {post['mood_color']}; 
                                    border-radius: 50%; margin-right: 10px;"></div>
                                    <span>{post['mood']}</span>
                                </div>
                            """, unsafe_allow_html=True)
                        
                        st.write(post['content'])
                        if st.button("提供支持", key=f"support_{post['id']}"):
                            with st.spinner('正在生成回应...'):
                                response = generate_response(post['content'], "anonymous_sharing")
                                st.write("AI支持回应：", response)
            else:
                st.info("还没有任何分享，来做第一个分享的人吧！")
        
        with tab3:
            # Get all posts for mood tracking
            posts = get_anonymous_posts()
            
            if not posts.empty:
                st.markdown("""
                    <div class="mood-tracker">
                        <h3>心情日历 📅</h3>
                        <p>在这里，你可以看到每一天的心情变化。方块的颜色代表那一天的心情，
                        悬停在方块上可以查看详细信息。</p>
                    </div>
                """, unsafe_allow_html=True)
                
                # Display calendar
                calendar_fig = create_mood_calendar(posts)
                if calendar_fig:
                    st.plotly_chart(calendar_fig, use_container_width=True)
                
                # Display mood tracking graph
                st.markdown("""
                    <div class="mood-tracker">
                        <h3>心情趋势 📈</h3>
                        <p>这条曲线展示了你的情绪变化趋势。点的颜色代表当天的心情，
                        曲线的高低表示心情的起伏。</p>
                    </div>
                """, unsafe_allow_html=True)
                
                mood_graph = create_mood_tracking_graph(posts)
                if mood_graph:
                    st.plotly_chart(mood_graph, use_container_width=True)
            else:
                st.info("还没有任何心情记录，发布一个带有心情的分享来开始追踪吧！")

    elif page == "我的故事":
        st.title("我的故事")
        
        # Explanation for history page
        st.markdown("""
        ### 你的成长轨迹 📝
        
        这里记录了你之前的所有对话和交流。
        回顾过去的对话可以帮助你看到自己的进步和成长。
        """)
        
        tab1, tab2 = st.tabs(["文化适应记录", "情感交流记录"])
        
        with tab1:
            cultural_container = st.container()
            for idx, message in enumerate(st.session_state.cultural_messages):
                col1, col2 = cultural_container.columns([0.9, 0.1])
                with col1:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                with col2:
                    if st.button("删除", key=f"delete_cultural_history_{idx}"):
                        del st.session_state.cultural_messages[idx]
                        st.experimental_rerun()
            
        with tab2:
            emotional_container = st.container()
            for idx, message in enumerate(st.session_state.emotional_messages):
                col1, col2 = emotional_container.columns([0.9, 0.1])
                with col1:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                with col2:
                    if st.button("删除", key=f"delete_emotional_history_{idx}"):
                        del st.session_state.emotional_messages[idx]
                        st.experimental_rerun()

    # Clear chat buttons in sidebar
    if st.sidebar.button("清除文化适应记录"):
        st.session_state.cultural_messages = []
        st.experimental_rerun()
        
    if st.sidebar.button("清除情感交流记录"):
        st.session_state.emotional_messages = []
        st.experimental_rerun()

if __name__ == "__main__":
    main()

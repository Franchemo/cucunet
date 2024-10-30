# Cultural Navigator Assistant (文化导航助手)

A Streamlit-based application designed to help international students navigate cultural differences and provide emotional support.

## Features

- 文化咨询 (Cultural Consultation)
- 情感支持 (Emotional Support)
- 匿名树洞 (Anonymous Sharing)
- 历史记录 (History Tracking)

## Setup Instructions

1. Clone the repository:
```bash
git clone https://github.com/yourusername/cultural_navigator_app.git
cd cultural_navigator_app
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
Create a `.env` file with:
```
OPENAI_API_KEY=your_openai_api_key
```

4. Run the application:
```bash
streamlit run app.py
```

## Deployment

This app is deployed on Streamlit Cloud. Visit [https://cultural-navigator.streamlit.app](https://cultural-navigator.streamlit.app) to use the application.

## Environment Variables

The following environment variables need to be set in Streamlit Cloud:
- `OPENAI_API_KEY`: Your OpenAI API key

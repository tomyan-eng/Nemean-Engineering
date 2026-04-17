import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import base64
from datetime import datetime

st.set_page_config(page_title="Nemean Inspector (Simple)", layout="wide")
st.title("🔍 Nemean Engineering Inspector (Simple Mode)")

# API key from secrets
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    key_configured = True
except:
    key_configured = False

# Session state
if "images_data" not in st.session_state:
    st.session_state.images_data = []

# Sidebar
with st.sidebar:
    st.header("Configuration")
    if not key_configured:
        api_input = st.text_input("Gemini API Key", type="password")
        if api_input:
            genai.configure(api_key=api_input)
            key_configured = True
    else:
        st.success("✅ API key loaded")
    
    st.markdown("---")
    prompt = st.text_area("Analysis prompt", value="""Analyze this construction photo. List:
- Deficiency
- Possible cause
- Recommended remedy
- Severity (Low/Medium/High)""", height=200)

# Helper
def analyze_image(img, notes, prompt_text):
    if not key_configured:
        return "❌ API key missing"
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        full_prompt = f"{prompt_text}\n\nInspector notes: {notes}\nAnalyze."
        response = model.generate_content([full_prompt, img])
        return response.text
    except Exception as e:
        return f"Error: {e}"

# Upload
st.subheader("Upload Photos")
uploaded = st.file_uploader("Choose images", type=["jpg","jpeg","png"], accept_multiple_files=True)
if uploaded:
    for file in uploaded:
        if not any(d["file_name"] == file.name for d in st.session_state.images_data):
            img = Image.open(file).convert("RGB")
            st.session_state.images_data.append({
                "image": img,
                "notes": "",
                "analysis": "",
                "file_name": file.name
            })
    st.success(f"{len(uploaded)} photo(s) added")

# Display and analyze
for idx, data in enumerate(st.session_state.images_data):
    col1, col2 = st.columns([1,2])
    with col1:
        st.image(data["image"], width=150)
    with col2:
        notes = st.text_area(f"Notes for {data['file_name']}", value=data["notes"], key=f"notes_{idx}")
        data["notes"] = notes
        if st.button(f"Analyze", key=f"analyze_{idx}"):
            with st.spinner("Analyzing..."):
                data["analysis"] = analyze_image(data["image"], notes, prompt)
                st.rerun()
        if data["analysis"]:
            st.markdown("**Analysis:**")
            st.markdown(data["analysis"])
    st.markdown("---")

# Generate report
if st.button("Generate Report"):
    if not st.session_state.images_data:
        st.warning("No photos")
    else:
        html = "<html><body>"
        html += f"<h1>Inspection Report {datetime.now()}</h1>"
        for i, d in enumerate(st.session_state.images_data):
            buff = io.BytesIO()
            d["image"].save(buff, format="JPEG")
            b64 = base64.b64encode(buff.getvalue()).decode()
            html += f"<h3>Photo {i+1}: {d['file_name']}</h3>"
            html += f'<img src="data:image/jpeg;base64,{b64}" width="300"><br>'
            html += f"<p><strong>Notes:</strong> {d['notes']}</p>"
            html += f"<p><strong>Analysis:</strong><br>{d['analysis'].replace(chr(10),'<br>')}</p><hr>"
        html += "</body></html>"
        st.download_button("Download Report", data=html, file_name="report.html", mime="text/html")

st.caption("Simple version – no Firebase, no project persistence.")

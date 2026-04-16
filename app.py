import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import base64
from datetime import datetime

st.set_page_config(page_title="OBC Engineering Inspector", layout="wide")
st.title("🏗️ Ontario Building Code (OBC) Inspection & Investigation")
st.markdown("Upload site photos → AI finds deficiencies, OBC/OFC violations, and remedies → Generate report")

# ---------- API Key: try secrets first, then sidebar ----------
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    key_configured = True
except:
    key_configured = False

# Sidebar
with st.sidebar:
    st.header("🔑 Configuration")
    if not key_configured:
        api_key_input = st.text_input("Google Gemini API Key", type="password", 
                                      help="Get free from aistudio.google.com")
        if api_key_input:
            genai.configure(api_key=api_key_input)
            key_configured = True
    else:
        st.success("✅ API key loaded from secrets (hidden)")
    
    st.markdown("---")
    st.subheader("📜 Ontario Codes & Standards")
    default_ontario_codes = """
Ontario Building Code (OBC) 2012 (as amended)
 - Division B: Section 9 (Housing), Section 5 (Environmental Separation), Section 4 (Structural)
Ontario Fire Code (OFC) – O. Reg. 213/07
CSA A440.2-19 (Windows/Doors)
CSA A23.1 (Concrete)
ASTM C920 (Sealants)
ASTM D6163 (Modified bitumen)
OBC 9.26 (Roof coverings)
OBC 9.27 (Cladding)
OBC 9.19 (Air leakage and vapour barriers)
OBC 5.4 (Moisture protection)
"""
    custom_codes = st.text_area("Reference codes (edit as needed)", 
                                value=default_ontario_codes.strip(), height=250)
    
    st.markdown("---")
    analysis_prompt = st.text_area("Analysis prompt", value="""You are a forensic engineering assistant in Ontario, Canada. 
For each site photo, identify:
1. Likely deficiencies (specific)
2. Relevant Ontario Building Code (OBC) or Ontario Fire Code (OFC) sections
3. Suggested remedies
4. Severity (Low/Medium/High/Critical)

Reference the codes provided. Use professional, bullet-point language for a report.""", height=200)
    
    if st.button("Clear all images"):
        st.session_state["images_data"] = []
        st.rerun()

# Session state
if "images_data" not in st.session_state:
    st.session_state["images_data"] = []

def analyze_image(image_pil, user_notes, codes_text, prompt_text):
    if not key_configured:
        return "❌ API key missing. Add in sidebar or configure secrets."
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        full = f"{prompt_text}\n\nCodes:\n{codes_text}\n\nInspector notes: {user_notes}\nAnalyze the photo."
        response = model.generate_content([full, image_pil])
        return response.text
    except Exception as e:
        return f"⚠️ Error: {e}"

# Upload area
col1, col2 = st.columns([1,1])
with col1:
    st.subheader("📸 Upload Photos")
    uploaded = st.file_uploader("Select images (JPG, PNG)", type=["jpg","jpeg","png"], accept_multiple_files=True)
    if uploaded:
        for file in uploaded:
            if not any(d["file_name"] == file.name for d in st.session_state["images_data"]):
                img = Image.open(file).convert("RGB")
                st.session_state["images_data"].append({
                    "image": img,
                    "notes": "",
                    "analysis": "",
                    "file_name": file.name
                })
        st.success(f"{len(uploaded)} photo(s) added.")
    
    # Display each with analysis button
    for idx, data in enumerate(st.session_state["images_data"]):
        with st.container():
            a, b = st.columns([1,2])
            with a:
                st.image(data["image"], width=150, caption=data["file_name"])
            with b:
                notes = st.text_area(f"Notes for {data['file_name']}", value=data["notes"], key=f"notes_{idx}")
                data["notes"] = notes
                if st.button(f"Analyze with OBC/OFC", key=f"analyze_{idx}"):
                    with st.spinner("Consulting OBC..."):
                        data["analysis"] = analyze_image(data["image"], notes, custom_codes, analysis_prompt)
                        st.rerun()
                if data["analysis"]:
                    st.markdown("**AI Findings (OBC/OFC):**")
                    st.markdown(data["analysis"])
            st.markdown("---")

# Report generation
with col2:
    st.subheader("📄 Generate OBC Site Report")
    analyzed = sum(1 for d in st.session_state["images_data"] if d["analysis"])
    st.info(f"📊 {analyzed}/{len(st.session_state['images_data'])} photos analyzed")
    
    title = st.text_input("Report title", value=f"OBC Inspection – {datetime.now().strftime('%Y-%m-%d')}")
    overall_notes = st.text_area("Overall notes (weather, scope, client)", height=100)
    
    if st.button("Generate Full Report", type="primary") and st.session_state["images_data"]:
        if not key_configured:
            st.error("API key required – add in sidebar or secrets")
        else:
            html = f"""
            <html><head><meta charset="UTF-8"><title>{title}</title>
            <style>body{{font-family: Arial; margin:40px}} .photo{{margin-bottom:30px}}</style>
            </head><body>
            <h1>{title}</h1>
            <p>Date: {datetime.now().strftime('%Y-%m-%d')}</p>
            <p><strong>Overall notes:</strong><br>{overall_notes.replace(chr(10),'<br>')}</p>
            <hr>
            """
            for i, d in enumerate(st.session_state["images_data"]):
                buff = io.BytesIO()
                d["image"].save(buff, format="JPEG")
                b64 = base64.b64encode(buff.getvalue()).decode()
                html += f"""
                <div class="photo">
                    <h3>Photo {i+1}: {d['file_name']}</h3>
                    <img src="data:image/jpeg;base64,{b64}" style="max-width:100%">
                    <p><strong>Inspector notes:</strong> {d['notes'] or '—'}</p>
                    <p><strong>AI analysis (OBC/OFC):</strong><br>{d['analysis'].replace(chr(10),'<br>') if d['analysis'] else 'Not analyzed'}</p>
                </div><hr>
                """
            html += "<p><i>Generated by OBC Engineering Inspector – always verify on site.</i></p></body></html>"
            st.session_state["final_report"] = html
            st.success("Report ready")
    
    if "final_report" in st.session_state and st.session_state["final_report"]:
        st.components.v1.html(st.session_state["final_report"], height=500, scrolling=True)
        b64 = base64.b64encode(st.session_state["final_report"].encode()).decode()
        st.markdown(f'<a href="data:text/html;base64,{b64}" download="{title.replace(" ","_")}.html">⬇️ Download HTML (print to PDF)</a>', unsafe_allow_html=True)

st.caption("**Ontario-specific** – references OBC, OFC, CSA, ASTM. API key stored securely in secrets.")

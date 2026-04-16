import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import base64
from datetime import datetime
import PyPDF2
import docx
from bs4 import BeautifulSoup
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="Nemean Engineering Inspector", layout="wide")
st.title("🔍 Engineering Inspector Pro")
st.markdown("Upload photos + reference documents → AI analyzes compliance → Generate custom report")

# ---------- API Key ----------
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    key_configured = True
except:
    key_configured = False

# ---------- Session state ----------
if "images_data" not in st.session_state:
    st.session_state["images_data"] = []          # each: {image, notes, analysis, file_name}
if "reference_text" not in st.session_state:
    st.session_state["reference_text"] = ""
if "report_template" not in st.session_state:
    st.session_state["report_template"] = None    # stores HTML string or None
if "batch_processing" not in st.session_state:
    st.session_state["batch_processing"] = False

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # API key fallback
    if not key_configured:
        api_key_input = st.text_input("Gemini API Key", type="password")
        if api_key_input:
            genai.configure(api_key=api_key_input)
            key_configured = True
    else:
        st.success("✅ API key loaded")
    
    st.markdown("---")
    
    # Mode selection: Code compliance or Contract compliance
    mode = st.radio("Compliance mode", ["Building Codes (OBC/OFC)", "Tender / CCDC Documents"])
    
    st.markdown("---")
    
    # Reference documents upload (for Tender/CCDC mode)
    if mode == "Tender / CCDC Documents":
        st.subheader("📄 Upload Reference Documents")
        ref_files = st.file_uploader("Upload PDF, DOCX, or TXT", type=["pdf", "docx", "txt"], accept_multiple_files=True)
        if ref_files:
            combined_text = ""
            for file in ref_files:
                try:
                    if file.type == "application/pdf":
                        reader = PyPDF2.PdfReader(file)
                        for page in reader.pages:
                            combined_text += page.extract_text() or ""
                    elif file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                        doc = docx.Document(file)
                        combined_text += "\n".join([para.text for para in doc.paragraphs])
                    else:  # txt
                        combined_text += file.read().decode("utf-8")
                except Exception as e:
                    st.error(f"Error reading {file.name}: {e}")
            st.session_state["reference_text"] = combined_text
            with st.expander("Preview extracted text"):
                st.text(combined_text[:1000] + ("..." if len(combined_text) > 1000 else ""))
        else:
            st.info("Upload tender or CCDC documents for contract compliance analysis.")
    else:
        # Code mode: show OBC reference (editable)
        default_obc = """
Ontario Building Code 2012: Section 9 (Housing), 5 (Environmental Separation)
Ontario Fire Code O.Reg 213/07
CSA A440.2 (Windows/Doors), CSA A23.1 (Concrete)
ASTM C920 (Sealants), ASTM D6163 (Modified bitumen)
OBC 9.26 (Roof coverings), 9.27 (Cladding), 5.4 (Moisture protection)
"""
        st.session_state["reference_text"] = st.text_area("Reference codes (editable)", value=default_obc.strip(), height=200)
    
    st.markdown("---")
    
    # Analysis prompt (editable)
    default_prompt = f"""You are an engineering compliance assistant.
Based on the provided reference {"codes" if mode == "Building Codes (OBC/OFC)" else "documents (tender/CCDC)"}, analyze each construction photo.
Output in this exact format:
- Deficiency: [specific observation]
- Compliance: [Compliant / Non-compliant / N/A]
- Reference: [cite the relevant clause/section from the reference]
- Remedy: [action if non-compliant]
- Severity: [Low/Medium/High/Critical]

Be concise. Do not add extra commentary."""
    
    analysis_prompt = st.text_area("Analysis prompt", value=default_prompt, height=200)
    
    # Report template upload
    st.markdown("---")
    st.subheader("📝 Report Template (optional)")
    template_file = st.file_uploader("Upload HTML or DOCX template", type=["html", "docx"])
    if template_file:
        try:
            if template_file.name.endswith(".html"):
                template_html = template_file.read().decode("utf-8")
                st.session_state["report_template"] = template_html
            elif template_file.name.endswith(".docx"):
                doc = docx.Document(template_file)
                template_html = "\n".join([para.text for para in doc.paragraphs])
                st.session_state["report_template"] = template_html
            st.success("Template loaded. Use placeholders like {{DATE}}, {{PHOTO_1}}, {{ANALYSIS_1}} etc.")
        except Exception as e:
            st.error(f"Template error: {e}")
    else:
        st.info("No template = default HTML report.")
    
    if st.button("🗑️ Clear all data"):
        st.session_state["images_data"] = []
        st.session_state["batch_processing"] = False
        st.rerun()

# ---------- Helper: Analyze one image ----------
def analyze_single_image(image_pil, user_notes, reference_text, prompt_text):
    if not key_configured:
        return "❌ API key missing."
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite")  # fast model
        full_prompt = f"{prompt_text}\n\nReference:\n{reference_text}\n\nInspector notes: {user_notes}\nAnalyze the photo."
        response = model.generate_content([full_prompt, image_pil])
        return response.text
    except Exception as e:
        return f"⚠️ Error: {e}"

# ---------- Batch analysis (parallel) ----------
def batch_analyze_all(images_list, reference_text, prompt_text, progress_bar):
    results = []
    total = len(images_list)
    # Use ThreadPoolExecutor to send requests concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_idx = {}
        for idx, img_data in enumerate(images_list):
            future = executor.submit(analyze_single_image, img_data["image"], img_data["notes"], reference_text, prompt_text)
            future_to_idx[future] = idx
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
            except Exception as e:
                result = f"Error: {e}"
            images_list[idx]["analysis"] = result
            results.append((idx, result))
            progress_bar.progress((len(results))/total)
    return images_list

# ---------- Main upload & analysis area ----------
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📸 Upload Photos")
    uploaded = st.file_uploader("Select images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
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
    
    # Display images with individual analysis buttons
    if st.session_state["images_data"]:
        for idx, data in enumerate(st.session_state["images_data"]):
            with st.container():
                a, b = st.columns([1, 2])
                with a:
                    st.image(data["image"], width=150, caption=data["file_name"])
                with b:
                    new_notes = st.text_area(f"Notes for {data['file_name']}", value=data["notes"], key=f"notes_{idx}")
                    data["notes"] = new_notes
                    if st.button(f"🔍 Analyze single", key=f"single_{idx}"):
                        with st.spinner("Analyzing..."):
                            data["analysis"] = analyze_single_image(
                                data["image"], data["notes"], st.session_state["reference_text"], analysis_prompt
                            )
                            st.rerun()
                    if data["analysis"]:
                        st.markdown("**Analysis:**")
                        st.markdown(data["analysis"])
                st.markdown("---")
        
        # Batch analysis button
        if st.button("⚡ Analyze all photos (batch)", type="primary"):
            if not st.session_state["reference_text"].strip():
                st.error("Please provide reference text (codes or documents) in sidebar.")
            else:
                st.session_state["batch_processing"] = True
                progress = st.progress(0)
                with st.spinner("Batch analyzing all photos (parallel requests)..."):
                    updated = batch_analyze_all(
                        st.session_state["images_data"],
                        st.session_state["reference_text"],
                        analysis_prompt,
                        progress
                    )
                    st.session_state["images_data"] = updated
                st.success("All photos analyzed!")
                st.session_state["batch_processing"] = False
                st.rerun()

# ---------- Report generation with custom template ----------
with col2:
    st.subheader("📄 Generate Report")
    analyzed_count = sum(1 for d in st.session_state["images_data"] if d["analysis"])
    st.info(f"📊 {analyzed_count}/{len(st.session_state['images_data'])} photos analyzed")
    
    report_title = st.text_input("Report title", value=f"Inspection Report – {datetime.now().strftime('%Y-%m-%d')}")
    project_info = st.text_area("Project details (address, client, inspector name)", height=80)
    
    if st.button("📝 Generate Report", type="primary") and st.session_state["images_data"]:
        if not key_configured:
            st.error("API key missing")
        else:
            # Prepare placeholders
            placeholders = {
                "DATE": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "TITLE": report_title,
                "PROJECT_INFO": project_info.replace("\n", "<br>"),
                "TOTAL_PHOTOS": str(len(st.session_state["images_data"]))
            }
            # Add per-photo placeholders
            for i, data in enumerate(st.session_state["images_data"], start=1):
                placeholders[f"PHOTO_{i}"] = f'<img src="data:image/jpeg;base64,{base64.b64encode(io.BytesIO(data["image"].tobytes()).getvalue()).decode()}" style="max-width:100%">'
                placeholders[f"NOTES_{i}"] = data["notes"] or "—"
                placeholders[f"ANALYSIS_{i}"] = data["analysis"] or "Not analyzed"
                placeholders[f"FILENAME_{i}"] = data["file_name"]
            
            # Use custom template if provided, else generate default HTML
            if st.session_state["report_template"]:
                html_output = st.session_state["report_template"]
                # Replace all placeholders {{KEY}}
                for key, value in placeholders.items():
                    html_output = html_output.replace(f"{{{{{key}}}}}", str(value))
            else:
                # Default HTML report
                html_output = f"""
                <html><head><meta charset="UTF-8"><title>{report_title}</title>
                <style>body{{font-family:Arial; margin:40px}} .photo{{margin-bottom:30px; border-bottom:1px solid #ccc}}</style>
                </head><body>
                <h1>{report_title}</h1>
                <p><strong>Generated:</strong> {placeholders['DATE']}</p>
                <p>{placeholders['PROJECT_INFO']}</p>
                <hr>
                """
                for i, data in enumerate(st.session_state["images_data"], start=1):
                    buff = io.BytesIO()
                    data["image"].save(buff, format="JPEG")
                    b64 = base64.b64encode(buff.getvalue()).decode()
                    html_output += f"""
                    <div class="photo">
                        <h3>Photo {i}: {data['file_name']}</h3>
                        <img src="data:image/jpeg;base64,{b64}" style="max-width:100%">
                        <p><strong>Notes:</strong> {data['notes'] or '—'}</p>
                        <p><strong>Analysis:</strong><br>{data['analysis'].replace(chr(10),'<br>') if data['analysis'] else 'Not analyzed'}</p>
                    </div><hr>
                    """
                html_output += "<p><i>Generated by Engineering Inspector Pro</i></p></body></html>"
            
            st.session_state["final_report"] = html_output
            st.success("Report generated")
    
    if "final_report" in st.session_state:
        st.components.v1.html(st.session_state["final_report"], height=500, scrolling=True)
        b64 = base64.b64encode(st.session_state["final_report"].encode()).decode()
        st.markdown(f'<a href="data:text/html;base64,{b64}" download="{report_title.replace(" ","_")}.html">⬇️ Download HTML (print to PDF)</a>', unsafe_allow_html=True)

st.caption("Enhanced version: batch analysis, document upload, custom templates. Uses gemini-2.5-flash-lite for speed.")

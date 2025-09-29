
#!pip install streamlit streamlit-mic-recorder openai-whisper transformers torch sentencepiece nltk
#!pip install pyngrok

"""Actual code uploaded to github"""

#!pip install streamlit streamlit-mic-recorder openai-whisper transformers torch sentencepiece nltk
#!pip install pyngrok

import os
import streamlit as st
from streamlit_mic_recorder import mic_recorder
from transformers import pipeline, AutoTokenizer
import tempfile
import nltk
from datetime import datetime

# ---- Force NLTK download ----
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

# ---- 1. State Management ----
if 'audio_data' not in st.session_state:
    st.session_state.audio_data = None
if 'file_name' not in st.session_state:
    st.session_state.file_name = None

def reset_app():
    st.session_state.audio_data = None
    st.session_state.file_name = None
    if 'recorder' in st.session_state:
        del st.session_state['recorder']
    if 'uploader' in st.session_state:
        st.session_state.uploader = None

# ---- 2. AI Models and Functions (Cached) ----
@st.cache_resource
def load_models():
    """Loads all AI models and tokenizers once."""
    summarizer = pipeline("summarization", model="t5-small")
    summarizer_tokenizer = AutoTokenizer.from_pretrained("t5-small")
    qg_pipe = pipeline("text2text-generation", model="BeIR/query-gen-msmarco-t5-base-v1")
    return summarizer, summarizer_tokenizer, qg_pipe

summarizer, summarizer_tokenizer, qg_pipe = load_models()

# ---- Helper Functions ----
def transcribe_with_whisper(audio_bytes):
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(temp_path, fp16=False)
        return result["text"]
    except Exception as e:
        return f"[Error: {str(e)}]"
    finally:
        os.remove(temp_path)

def generate_summary(text):
    inputs = summarizer_tokenizer(text, max_length=1024, truncation=True, return_tensors="pt")
    summary_ids = summarizer.model.generate(inputs['input_ids'], num_beams=4, max_length=150, early_stopping=True)
    return summarizer_tokenizer.decode(summary_ids[0], skip_special_tokens=True)

def generate_flashcards(text):
    sentences = nltk.sent_tokenize(text)
    good_sentences = [sent for sent in sentences if 50 > len(sent.split()) > 10]
    if not good_sentences: return []
    flashcards = []
    for sentence in good_sentences[:10]:
        try:
            generated_text = qg_pipe(sentence, max_length=64, do_sample=True)[0]['generated_text']
            flashcards.append({"question": generated_text.strip(), "answer": sentence.strip()})
        except Exception:
            continue
    return flashcards

# ---- 3. Main App UI and Logic ----
st.title("Lecture Voice-to-Notes Generator (Free Tools)")

if st.session_state.audio_data is None:
    st.write("Record live audio or upload a lecture file to begin.")
    tab1, tab2 = st.tabs(["🎤 Microphone", "📁 Upload Audio"])

    with tab1:
        audio = mic_recorder(start_prompt="🎙️ Start Recording", stop_prompt="⏹️ Stop", format="webm", key='recorder')
        if audio and audio['bytes']:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.session_state.file_name = f"recording_{timestamp}.webm"
            st.session_state.audio_data = audio['bytes']
            st.rerun()

    with tab2:
        audio_file = st.file_uploader("Upload lecture audio...", type=["wav", "mp3", "webm","m4a"], key='uploader')
        if audio_file:
            st.session_state.file_name = audio_file.name
            st.session_state.audio_data = audio_file.read()
            st.rerun()
else:
    st.subheader(f"Analysis for: `{st.session_state.file_name}`")
    st.audio(st.session_state.audio_data)

    # --- THE FIX: Provide a copyable filename for the user ---
    st.write("Your browser might assign a random name to the download. Please use the suggested filename below.")
    st.code(st.session_state.file_name, language=None)
    
    st.download_button(
        label="Download Audio File",
        data=st.session_state.audio_data,
        file_name=st.session_state.file_name, # Still suggest the name
        mime="audio/webm"
    )
    # --- END OF FIX ---

    with st.spinner("Transcribing audio... (This may take several minutes)"):
        transcription = transcribe_with_whisper(st.session_state.audio_data)

    st.subheader("Transcription")
    st.write(transcription)

    if transcription and not transcription.startswith("[Error"):
        with st.spinner("Summarizing and generating study materials..."):
            summary = generate_summary(transcription)
            flashcards = generate_flashcards(transcription)

        st.subheader("Summary")
        st.info(summary)

        if flashcards:
            st.subheader("Flashcards / Quiz")
            for card in flashcards:
                st.write(f"**Q:** {card['question']}")
                st.write(f"**A:** {card['answer']}")
        else:
            st.write("_No quizzes generated for this input._")
        st.success("Done!")
    else:
        st.error("Could not process the audio.")

    st.button("Start Over", on_click=reset_app)

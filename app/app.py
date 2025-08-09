import streamlit as st
from engine.model import ask_llm
from engine.storage import DB
from engine.adapt import pick_next_skill, update_progress

st.set_page_config(page_title="Buddy", page_icon="🎒", layout="centered")
st.title("Buddy - Accessible Education")

db = DB()

if "learner" not in st.session_state:
    with st.form("setup"):
        name = st.text_input("Your name")
        lang = st.selectbox("Language", ["English"])
        subject = st.selectbox("Subject", ["Math", "Science", "Literacy"])
        level = st.selectbox("Level", ["Beginner", "Intermediate", "Advanced"])
        start = st.form_submit_button("Let's Go")
    if start and name:
        st.session_state.learner = db.ensure_learner(name, lang)
        st.session_state.subject = subject
        st.session_state.level = level
        st.rerun()

if "learner" in st.session_state:
    skill = pick_next_skill(db, st.session_state.learner, st.session_state.subject)
    st.subheader(f"{st.session_state.subject}: {skill['topic']} -> {skill['subtopic']}")

    if "turn" not in st.session_state:
        prompt = (
            f"You are Buddy, a patient offline tutor for {st.session_state.subject}. "
            f"Student level: {st.session_state.level}. Language: English. "
            f"Goal: Teach {skill['subtopic']} with one example, then ask ONE question."
        )
        st.session_state.turn = ask_llm(prompt)
    
    st.markdown(st.session_state.turn)

    with st.form("answer"):
        ans = st.text_input("Your answer")
        submitted = st.form_submit_button("Submit")
    if submitted and ans.strip():
        feedback = ask_llm(
            f"Student answered: {ans}\nProvide step-by-step feedback and a hint."
        )
        st.markdown(feedback)
        correct = "correct" in feedback.lower()
        update_progress(db, st.session_state.learner, skill, correct)
        st.session_state.turn = ask_llm(
            f"Give a follow-up single question on {skill['subtopic']} at {st.session_state.level} level."
        )
        st.rerun()
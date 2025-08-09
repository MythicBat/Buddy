import streamlit as st
from engine.model import ask_llm, ask_llm_json
from engine.storage import DB
from engine.adapt import pick_next_skill, update_progress
from engine.curriculum import load_pack, merge_pack_into_db

st.set_page_config(page_title="Buddy", page_icon="🎒", layout="centered")
st.title("🎒 Buddy — Accessible Education")

db = DB()

# ---- SIDEBAR ----
with st.sidebar:
    st.header("Settings")
    st.session_state.setdefault("lang", "English")
    st.session_state.lang = st.selectbox("Language", ["English"], index=["English"].index(st.session_state.lang))
    st.markdown("---")
    up = st.file_uploader("Import curriculum pack (.json)", type=["json"])
    if up is not None:
        try:
            pack = load_pack(up)
            merge_pack_into_db(db, pack)
            st.success(f"Imported pack for {pack['subject']} with {len(pack['skills'])} skills.")
        except Exception as e:
            st.error(f"Import failed: {e}")

# ---- SETUP ----
if "learner" not in st.session_state:
    with st.form("setup"):
        name = st.text_input("Your name")
        subject = st.selectbox("Subject", ["Math", "Science", "Literacy"])
        level = st.selectbox("Level", ["Beginner","Intermediate","Advanced"])
        start = st.form_submit_button("Start")
    if start and name:
        st.session_state.learner = db.ensure_learner(name, st.session_state.lang)
        st.session_state.subject = subject
        st.session_state.level = level
        st.session_state.mode = "diagnostic"
        st.session_state.diag_q = 0
        st.session_state.diag_score = 0
        st.rerun()

# ---- DIAGNOSTIC (3 quick questions) ----
def gen_diag_question(subject, level, lang):
    j = ask_llm_json(
        system_goal="Create one short diagnostic question.",
        user_task=f"Subject: {subject}. Level: {level}. Language: {lang}. Make it concise.",
        schema_hint='{"question": "string"}'
    )
    return j.get("question", "Start with 2+3 = ?")

def eval_answer(question, student_answer, level, lang):
    j = ask_llm_json(
        system_goal="Judge the student's answer and produce feedback and a follow-up.",
        user_task=f"Question: {question}\nStudent: {student_answer}\nLevel: {level}\nLanguage: {lang}\nBe strict but kind.",
        schema_hint='{"correct": true/false, "feedback": "string", "next_question": "string"}'
    )
    # defaults if parsing fails
    if "correct" not in j: j["correct"] = "correct" in str(j).lower()
    if "feedback" not in j: j["feedback"] = "Thanks! Here is some feedback."
    if "next_question" not in j: j["next_question"] = "Try 4+3 = ?"
    return j

if "learner" in st.session_state and st.session_state.mode == "diagnostic":
    st.info("Quick check: 3 questions to set your starting point.")
    if "diag_q_text" not in st.session_state:
        st.session_state.diag_q_text = gen_diag_question(st.session_state.subject, st.session_state.level, st.session_state.lang)

    st.write(f"**Q{st.session_state.diag_q+1}:** {st.session_state.diag_q_text}")
    with st.form("diag"):
        ans = st.text_input("Your answer")
        go = st.form_submit_button("Submit")
    if go and ans.strip():
        res = eval_answer(st.session_state.diag_q_text, ans, st.session_state.level, st.session_state.lang)
        st.markdown(res["feedback"])
        st.session_state.diag_score += int(bool(res["correct"]))
        st.session_state.diag_q += 1
        if st.session_state.diag_q >= 3:
            # adjust level roughly
            score = st.session_state.diag_score
            if score <= 1: st.session_state.level = "Beginner"
            elif score == 2: st.session_state.level = "Intermediate"
            else: st.session_state.level = "Advanced"
            st.success(f"Diagnostic done! Starting level: **{st.session_state.level}**")
            st.session_state.mode = "lesson"
            for k in ("diag_q_text",): st.session_state.pop(k, None)
        else:
            st.session_state.diag_q_text = res["next_question"]
        st.rerun()

# ---- LESSON LOOP ----
if "learner" in st.session_state and st.session_state.mode == "lesson":
    skill = pick_next_skill(db, st.session_state.learner, st.session_state.subject)
    st.subheader(f"{st.session_state.subject}: {skill['topic']} → {skill['subtopic']}")

    if "turn" not in st.session_state:
        prompt = (
            f"You are Buddy, a patient offline tutor for {st.session_state.subject}. "
            f"Student level: {st.session_state.level}. Language: {st.session_state.lang}. "
            f"Goal: Teach {skill['subtopic']} with one short example, then ask ONE question."
        )
        st.session_state.turn = ask_llm(prompt)

    st.markdown(st.session_state.turn)

    with st.form("answer"):
        ans = st.text_input("Your answer")
        submitted = st.form_submit_button("Submit")
    if submitted and ans.strip():
        res = eval_answer(st.session_state.turn, ans, st.session_state.level, st.session_state.lang)
        st.markdown(res["feedback"])
        correct = bool(res["correct"])
        update_progress(db, st.session_state.learner, skill, correct)
        st.session_state.turn = res["next_question"]
        st.rerun()
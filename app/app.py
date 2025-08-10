from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

import streamlit as st
from engine.model import ask_llm, ask_llm_json
from engine.storage import DB
from engine.adapt import pick_next_skill, update_progress
from engine.curriculum import load_pack, merge_pack_into_db
from engine.safety import check_user_input

# ---------------- UI SETUP ----------------
st.set_page_config(page_title="Buddy", page_icon="🎒", layout="centered")
st.title("🎒 Buddy — Accessible Education")

db = DB()
db.ensure_badges_seed()

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.header("Settings")
    st.session_state.setdefault("lang", "English")
    st.session_state.lang = st.selectbox("Language", ["English"], index=0)

    st.markdown("---")
    up = st.file_uploader("Import curriculum pack (.json)", type=["json"])
    if up is not None:
        try:
            pack = load_pack(up)
            merge_pack_into_db(db, pack)
            st.success(f"Imported **{pack['subject']}** pack with {len(pack['skills'])} skills.")
        except Exception as e:
            st.error(f"Import failed: {e}")

# ---------------- HELPERS ----------------
def gen_diag_question(subject, level, lang):
    j = ask_llm_json(
        system_goal="Create ONE short diagnostic question.",
        user_task=f"Subject: {subject}. Level: {level}. Language: {lang}. Keep it concise and objective.",
        schema_hint='{"question": "string"}'
    )
    return j.get("question", "What is 2 + 3?")

def eval_answer(question, student_answer, level, lang):
    j = ask_llm_json(
        system_goal="Judge answer; give step-by-step feedback; return a follow-up question.",
        user_task=(
            f"Question: {question}\n"
            f"Student answer: {student_answer}\n"
            f"Level: {level}\nLanguage: {lang}\n"
            "Be strict but kind. Keep feedback short."
        ),
        schema_hint='{"correct": true/false, "feedback": "string", "next_question": "string"}'
    )
    # minimal fallbacks
    if "correct" not in j:
        j["correct"] = "correct" in str(j).lower()
    j.setdefault("feedback", "Thanks! Here is some feedback and a small hint.")
    j.setdefault("next_question", "Try 4 + 3 = ?")
    return j

def start_session(name, subject, level):
    st.session_state.learner = db.ensure_learner(name, st.session_state.lang)
    st.session_state.subject = subject
    st.session_state.level = level
    st.session_state.mode = "diagnostic"
    st.session_state.diag_q = 0
    st.session_state.diag_score = 0
    st.session_state.diag_q_text = gen_diag_question(subject, level, st.session_state.lang)

# ---------------- TABS ----------------
tab_learn, tab_progress = st.tabs(["📘 Learn", "🎖️ Progress"])

with tab_learn:
    # ----- Setup form (if needed) -----
    if "learner" not in st.session_state:
        with st.form("setup"):
            name = st.text_input("Your name")
            subject = st.selectbox("Subject", ["Math", "Science", "Literacy"])
            level = st.selectbox("Level", ["Beginner", "Intermediate", "Advanced"])
            start = st.form_submit_button("Start")
        if start and name.strip():
            start_session(name.strip(), subject, level)
            st.rerun()
        st.stop()

    # ----- Diagnostic flow -----
    if st.session_state.mode == "diagnostic":
        st.info("Quick check: 3 short questions to set your starting level.")
        st.write(f"**Q{st.session_state.diag_q + 1}:** {st.session_state.diag_q_text}")

        with st.form("diag"):
            ans = st.text_input("Your answer")
            go = st.form_submit_button("Submit")
        if go and ans.strip():
            ok, msg = check_user_input(ans)
            if not ok:
                st.warning(msg)
                st.stop()

            res = eval_answer(st.session_state.diag_q_text, ans, st.session_state.level, st.session_state.lang)
            st.markdown(res["feedback"])
            st.session_state.diag_score += int(bool(res["correct"]))
            st.session_state.diag_q += 1

            if st.session_state.diag_q >= 3:
                score = st.session_state.diag_score
                if score <= 1:
                    st.session_state.level = "Beginner"
                elif score == 2:
                    st.session_state.level = "Intermediate"
                else:
                    st.session_state.level = "Advanced"
                st.success(f"Diagnostic done! Starting level: **{st.session_state.level}**")
                st.session_state.mode = "lesson"
                for k in ("diag_q_text",):
                    st.session_state.pop(k, None)
            else:
                st.session_state.diag_q_text = res["next_question"]
            st.rerun()

    # ----- Lesson loop -----
    if st.session_state.mode == "lesson":
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
            ok, msg = check_user_input(ans)
            if not ok:
                st.warning(msg)
                st.stop()

            res = eval_answer(st.session_state.turn, ans, st.session_state.level, st.session_state.lang)
            st.markdown(res["feedback"])
            correct = bool(res["correct"])
            earned = update_progress(db, st.session_state.learner, skill, correct)

            # badge notification
            if earned:
                try:
                    st.toast("🎖️ Badge unlocked: " + ", ".join(earned), icon="🎉")
                except Exception:
                    st.success("🎖️ Badge unlocked: " + ", ".join(earned))

            # next question (continue the conversation)
            st.session_state.turn = res["next_question"]
            st.rerun()

with tab_progress:
    if "learner" not in st.session_state:
        st.info("Start a session in the Learn tab first.")
    else:
        stats = db.learner_stats(st.session_state.learner)
        c1, c2, c3 = st.columns(3)
        c1.metric("Answered", stats["answered"])
        c2.metric("Correct", stats["correct"])
        acc = f"{(stats['correct']/stats['answered']*100):.0f}%" if stats["answered"] else "—"
        c3.metric("Accuracy", acc)

        st.subheader("Mastered/Practicing skills")
        st.write(f"{stats['mastered']} skill(s) at Practicing/Mastered status")

        st.subheader("Badges")
        if not stats["badges"]:
            st.write("No badges yet — keep learning!")
        else:
            for b in stats["badges"]:
                st.markdown(f"- **{b['name']}** — {b['desc']}")
from pathlib import Path
import sys, os, tempfile, json, time
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from streamlit_mic_recorder import mic_recorder

from engine.model import ask_llm, ask_llm_json
from engine.storage import DB
from engine.adapt import pick_next_skill, update_progress
from engine.curriculum import load_pack, merge_pack_into_db
from engine.safety import check_user_input
from engine.audio import tts_save_wav, stt_transcribe_wav

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

    # default path for the offline Vosk STT model
    st.session_state.setdefault("vosk_path", "models/vosk-model-small-en-us-0.15")
    st.caption(f"Vosk model path: `{st.session_state.vosk_path}`")

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
        system_goal="Judge the student's answer; give step-by-step feedback; return a follow-up question.",
        user_task=(
            f"Question: {question}\n"
            f"Student answer: {student_answer}\n"
            f"Level: {level}\nLanguage: {lang}\n"
            "Be strict but kind. Keep feedback short."
        ),
        schema_hint='{"correct": true/false, "feedback": "string", "next_question": "string"}'
    )
    if "correct" not in j:
        j["correct"] = "correct" in str(j).lower()
    j.setdefault("feedback", "Thanks! Here is a short explanation and a hint.")
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
tab_learn, tab_progress, tab_teacher = st.tabs(["📘 Learn", "🎖️ Progress", "🧑‍🏫 Teacher"])

# ======== LEARN TAB ========
with tab_learn:
    voice_mode = st.toggle("🎤 Voice mode (offline)", value=False, help="Use TTS and mic recording with offline STT")

    # Setup form
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

    # Diagnostic flow
    if st.session_state.mode == "diagnostic":
        st.info("Quick check: 3 short questions to set your starting level.")
        st.write(f"**Q{st.session_state.diag_q + 1}:** {st.session_state.diag_q_text}")

        if voice_mode:
            cols = st.columns(2)
            with cols[0]:
                if st.button("🔊 Speak the question"):
                    with tempfile.TemporaryDirectory() as td:
                        out_wav = os.path.join(td, "buddy_says.wav")
                        tts_save_wav(st.session_state.diag_q_text, out_wav)
                        st.audio(open(out_wav, "rb").read(), format="audio/wav")
            with cols[1]:
                audio = mic_recorder(start_prompt="🎙️ Record answer", stop_prompt="⏹️ Stop", just_once=True, key="diag_mic")
                if audio and audio.get("bytes"):
                    with tempfile.TemporaryDirectory() as td:
                        rec_path = os.path.join(td, "user.wav")
                        with open(rec_path, "wb") as f:
                            f.write(audio["bytes"])
                        transcript = stt_transcribe_wav(rec_path, st.session_state.vosk_path)
                        st.session_state["prefill_answer"] = transcript
                        st.info(f"Transcribed: **{transcript}**")

        default_ans = st.session_state.pop("prefill_answer", "") if "prefill_answer" in st.session_state else ""
        with st.form("diag"):
            ans = st.text_input("Your answer", value=default_ans)
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

    # Lesson loop
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

        # Voice controls
        if voice_mode:
            colA, colB = st.columns(2)
            with colA:
                if st.button("🔊 Speak the question"):
                    with tempfile.TemporaryDirectory() as td:
                        out_wav = os.path.join(td, "buddy_says.wav")
                        tts_save_wav(st.session_state.turn, out_wav)
                        st.audio(open(out_wav, "rb").read(), format="audio/wav")
            with colB:
                audio = mic_recorder(start_prompt="🎙️ Record answer", stop_prompt="⏹️ Stop", just_once=True, key="lesson_mic")
                if audio and audio.get("bytes"):
                    with tempfile.TemporaryDirectory() as td:
                        rec_path = os.path.join(td, "user.wav")
                        with open(rec_path, "wb") as f:
                            f.write(audio["bytes"])
                        transcript = stt_transcribe_wav(rec_path, st.session_state.vosk_path)
                        st.session_state["prefill_answer"] = transcript
                        st.info(f"Transcribed: **{transcript}**")

        st.markdown(st.session_state.turn)

        default_ans = st.session_state.pop("prefill_answer", "") if "prefill_answer" in st.session_state else ""
        with st.form("answer"):
            ans = st.text_input("Your answer", value=default_ans)
            submitted = st.form_submit_button("Submit")

        if submitted and ans.strip():
            ok, msg = check_user_input(ans)
            if not ok:
                st.warning(msg)
                st.stop()

            res = eval_answer(st.session_state.turn, ans, st.session_state.level, st.session_state.lang)
            st.markdown(res["feedback"])

            # ---- Report content button ----
            with st.expander("Report content", expanded=False):
                reason = st.text_input("Why are you reporting this?")
                if st.button("Submit report"):
                    db.log_event(st.session_state.learner, skill["id"], "report",
                                 json.dumps({"reason": reason, "ts": int(time.time())}))
                    st.success("Thanks — your report was recorded.")

            correct = bool(res["correct"])
            earned = update_progress(db, st.session_state.learner, skill, correct)
            if earned:
                try:
                    st.toast("🎖️ Badge unlocked: " + ", ".join(earned), icon="🎉")
                except Exception:
                    st.success("🎖️ Badge unlocked: " + ", ".join(earned))

            st.session_state.turn = res["next_question"]
            st.rerun()

# ======== PROGRESS TAB ========
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
        st.write(f"{stats['mastered']} skill(s) mastered/practicing")

        st.subheader("Badges")
        if not stats["badges"]:
            st.write("No badges yet — keep learning!")
        else:
            for b in stats["badges"]:
                st.markdown(f"- **{b['name']}** — {b['desc']}")

# ======== TEACHER TAB ========
with tab_teacher:
    st.subheader("Manage skills & content packs")

    manage_subject = st.selectbox("Subject to manage", ["Math", "Science", "Literacy"])

    st.markdown("### Add a new skill")
    with st.form("add_skill"):
        t = st.text_input("Topic", placeholder="e.g., Arithmetic")
        sub = st.text_input("Subtopic", placeholder="e.g., Add 2-digit numbers")
        add = st.form_submit_button("Add skill")
    if add and t.strip() and sub.strip():
        if not db.skill_exists(manage_subject, t.strip(), sub.strip()):
            db.insert_skill(manage_subject, t.strip(), sub.strip())
            st.success("Skill added.")
        else:
            st.info("That skill already exists.")

    st.markdown("### Existing skills")
    skills = db.list_skills(manage_subject)
    if not skills:
        st.write("No skills yet.")
    else:
        for s in skills:
            cols = st.columns([3, 4, 2])
            cols[0].write(f"**{s['topic']}**")
            cols[1].write(s["subtopic"])
            if cols[2].button("Delete", key=f"del-{s['id']}"):
                db.delete_skill(s["id"])
                st.rerun()

    st.markdown("---")
    st.markdown("### Export this subject as a curriculum pack (.json)")
    if st.button("Export pack"):
        pack = db.export_pack(manage_subject)
        st.download_button(
            "Download JSON",
            data=json.dumps(pack, indent=2).encode("utf-8"),
            file_name=f"{manage_subject.lower()}_pack.json",
            mime="application/json"
        )
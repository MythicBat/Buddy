import sqlite3, time

class DB:
    def __init__(self, path="buddy.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init()
    
    def _init(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS learners(
                                id INTEGER PRIMARY KEY,
                                name TEXT,
                                lang TEXT,
                                created_at INTEGER);
        CREATE TABLE IF NOT EXISTS skills(
                                id INTEGER PRIMARY KEY,
                                subject TEXT,
                                topic TEXT,
                                subtopic TEXT);
        CREATE TABLE IF NOT EXISTS progress(
                                learner_id INT,
                                skill_id INT,
                                status TEXT,
                                streak_correct INT,
                                last_seen INT,
                                PRIMARY KEY(learner_id, skill_id));
        CREATE TABLE IF NOT EXISTS events(
                                id INTEGER PRIMATY KEY,
                                learner_id INT, skill_id INT,
                                kind TEXT,
                                data TEXT,
                                created_at INTEGER);
        CREATE TABLE IF NOT EXISTS badges(
                                id INTEGER PRIMARY KEY,
                                code TEXT UNIQUE,
                                name TEXT,
                                description TEXT);
        CREATE TABLE IF NOT EXISTS learner_badges(
                                learner_id INT,
                                badge_code TEXT,
                                earned_at INTEGER,
                                PRIMARY KEY(learner_id, badge_code));
                                """)
        self.conn.commit()
    
    def ensure_learner(self, name, lang):
        cur = self.conn.execute(
            "SELECT id FROM learners WHERE name=? AND lang=?", (name, lang)
        )
        row = cur.fetchone()
        if row: return row[0]
        self.conn.execute(
            "INSERT INTO learners(name, lang, created_at) VALUES(?,?,?)",
            (name, lang, int(time.time()))
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    def skills_for(self, subject):
        cur = self.conn.execute(
            "SELECT id, topic, subtopic FROM skills WHERE subject=?", (subject,)
        )
        rows = cur.fetchall()
        if not rows:
            seed = [
                ("Math", "Arithmetic", "Add 1-digit numbers"),
                ("Science", "Matter", "Solid vs Liquid"),
                ("Literacy", "Reading", "Short vowel sounds")
            ]
            for s in seed:
                self.conn.execute(
                    "INSERT INTO skills(subject, topic, subtopic) VALUES(?,?,?)", s
                )
            self.conn.commit()
            return self.skills_for(subject)
        return [{"id":r[0], "topic":r[1], "subtopic":r[2]} for r in rows]
    
    def bump_progress(self, learner_id, skill_id, correct):
        cur = self.conn.execute(
            "SELECT status, streak_correct FROM progress WHERE learner_id=? AND skill_id=?",
            (learner_id, skill_id)
        )
        row = cur.fetchone()
        status, streak = (row if row else ("Learning", 0))
        streak = (streak + 1) if correct else 0
        if streak >= 3: status = "Practicing"
        self.conn.execute(
            """
            INSERT INTO progress(learner_id, skill_id, status, streak_correct, last_seen)
            VALUES(?,?,?,?)
            ON CONFLICT(learner_id, skill_id) DO UPDATE SET
                status=excluded.status,
                streak_correct=excluded.streak_correct,
                last_seen=excluded.last_seen
            """, (learner_id, skill_id, status, streak, int(time=time()))
        )
        self.conn.commit()
    
    def skill_exists(self, subject, topic, subtopic):
        cur = self.conn.execute(
            "SELECT 1 FROM skills WHERE subject=? AND topic=? AND subtopic=?",
            (subject, topic, subtopic)
        )
        return cur.fetchone() is not None
    
    def insert_skill(self, subject, topic, subtopic):
        self.conn.execute(
            "INSERT INTO skills(subject, topic, subtopic) VALUES(?,?,?)",
            (subject, topic, subtopic)
        )
        self.conn.commit()
    
    def log_event(self, learner_id, skill_id, kind, data_json="{}"):
        import time, json
        self.conn.execute(
            "INSERT INTO events(learner_id, skill_id, kind, data, created_at) VALUES(?,?,?,?)",
            (learner_id, skill_id, kind, data_json, int(time=time()))
        )
        self.conn.commit()
    
    def ensure_badges_seed(self):
        rows = self.conn.execute("SELECT COUNT(*) FROM badges").fetchone()[0]
        if rows: return
        seed = [
            ("FIRST_5", "First Five", "Answered 5 questions"),
            ("STREAK_3", "On a Roll", "3 correct in a row"),
            ("MASTER_1", "Master I", "Mastered one skill"),
        ]
        for code, name, desc in seed:
            self.conn.execute(
                "INSERT INTO badges(code, name, description) VALUES(?,?,?)",
                (code, name, desc)
            )
        self.conn.commit()
    
    def award_badge(self, learner_id, code):
        import time
        cur = self.conn.execute(
            "SELECT 1 FROM learner_badges WHERE learner_id=? AND badge_code=?",
            (learner_id, code)
        ).fetchone()
        if cur: return False
        self.conn.execute(
            "INSERT INTO learner_badges(learner_id, badge_code, earned_at) VALUES(?,?,?)",
            (learner_id, code, int(time=time()))
        )
        self.conn.commit()
        return True
    
    def learner_stats(self, learner_id):
        total = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE learner_id=? AND kind='answer'",
            (learner_id,)
        ).fetchone()[0]
        correct = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE learner_id=? AND kind='answer' AND json_extract(data, '$.correct')=1",
            (learner_id,)
        ).fetchone()[0]
        mastered = self.conn.execute(
            "SELECT COUNT(*) FROM progress WHERE learner_id=? AND status='Practicing'",
            (learner_id,)
        ).fetchone()[0]
        badges = self.conn.execute(
            "SELECT b.code, b.name, b.description, lb.earned_at FROM learner_badges lb JOIN badges b ON b.code=lb.badge_code WHERE learner_id=?",
            (learner_id,)
        ).fetchall()
        return {"answered": total, "correct": correct, "mastered": mastered,
                "badges": [{"code":r[0], "name":r[1], "desc":r[2], "ts":r[3]} for r in badges]}
    
    def streak_correct(self, learner_id):
        # Last contiguous correct answers
        cur = self.conn.execute("""
            SELECT json_extract(data, '$.correct') FROM events
            WHERE learner_id=? AND kind='answer'
            ORDER BY id DESC LIMIT 20
            """, (learner_id))
        streak = 0
        for (c,) in cur.fetchall():
            if c == 1: streak += 1
            else: break
        return streak
    
    def list_skills(self, subject: str):
        cur = self.conn.execute(
            "SELECT id, topic, subtopic FROM skills WHERE subject=? ORDER BY topic, subtopic",
            (subject,)
        )
        return [{"id":r[0], "topic":r[1], "subtopic":r[2]} for r in cur.fetchall()]
    
    def delete_skills(self, skill_id: int):
        self.conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
        self.conn.commit()
    
    def export_pack(self, subject: str) -> dict:
        skills = self.list_skills(subject)
        return {
            "subject": subject,
            "version": "v1",
            "skills": [{"topic": s["topic"], "subtopic": s["subtopic"]} for s in skills]
        }
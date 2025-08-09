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
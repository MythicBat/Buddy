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
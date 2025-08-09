import json

def load_pack(fp) -> dict:
    data = json.load(fp)
    #minimal validation
    subj = data.get("subject")
    skills = data.get("skills", [])
    assert subj and isinstance(skills, list), "Invalid curriculum pack"
    return data

def merge_pack_into_db(db, pack: dict):
    subject = pack["subject"]
    for sk in pack["skills"]:
        topic = sk["topic"]; sub = sk["subtopic"]
        # Insert if not exists
        if not db.skill_exists(subject, topic, sub):
            db.insert_skill(subject, topic, sub)
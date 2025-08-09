import random

def pick_next_skill(db, learner_id, subject):
    skills = db.skills_for(subject)
    return random.choice(skills)

def update_progress(db, learner_id, skill, correct: bool):
    db.bump_progress(learner_id, skill["id"], correct)
BLOCKLIST = ["violence", "self-harm", "sex", "drugs", "weapon", "terror", "gambling"]

def check_user_input(text: str) -> tuple[bool, str]:
    t = text.lower()
    for w in BLOCKLIST:
        if w in t:
            return False, "I can't help you with that. Let's focus on learning topics."
    return True, ""

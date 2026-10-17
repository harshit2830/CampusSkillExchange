"""Explainable skill matching shared by the web application and AIP demo."""


def rank_matches(student, skills):
    """Return one result per peer, scoring each complementary direction 50%.

    ``student`` and ``skills`` are dictionaries. Skills contain ``student_id``,
    ``skill_name``, and ``skill_type`` (``teach`` or ``learn``).
    """
    own_teaches = {
        skill["skill_name"].strip().casefold()
        for skill in skills
        if skill["student_id"] == student["id"] and skill["skill_type"] == "teach"
    }
    own_learns = {
        skill["skill_name"].strip().casefold()
        for skill in skills
        if skill["student_id"] == student["id"] and skill["skill_type"] == "learn"
    }
    peers = {}
    for skill in skills:
        peer_id = skill["student_id"]
        if peer_id == student["id"]:
            continue
        peer = peers.setdefault(
            peer_id,
            {"student": skill["student"], "teaches": set(), "learns": set()},
        )
        peer["teaches" if skill["skill_type"] == "teach" else "learns"].add(
            skill["skill_name"].strip().casefold()
        )

    results = []
    for peer_id, peer in peers.items():
        learn_matches = own_learns & peer["teaches"]
        teach_matches = own_teaches & peer["learns"]
        if not learn_matches and not teach_matches:
            continue
        score = (50 if learn_matches else 0) + (50 if teach_matches else 0)
        results.append(
            {
                "student_id": peer_id,
                "student": peer["student"],
                "score": score,
                "skills_they_teach": sorted(learn_matches),
                "skills_you_teach": sorted(teach_matches),
            }
        )
    return sorted(results, key=lambda result: (-result["score"], result["student"].casefold()))


def main():
    sample_students = [
        {"id": 1, "student": "Aarav"},
        {"id": 2, "student": "Maya"},
        {"id": 3, "student": "Ishaan"},
    ]
    sample_skills = [
        {"student_id": 1, "student": "Aarav", "skill_name": "Python", "skill_type": "teach"},
        {"student_id": 1, "student": "Aarav", "skill_name": "Public Speaking", "skill_type": "learn"},
        {"student_id": 2, "student": "Maya", "skill_name": "Public Speaking", "skill_type": "teach"},
        {"student_id": 2, "student": "Maya", "skill_name": "Python", "skill_type": "learn"},
        {"student_id": 3, "student": "Ishaan", "skill_name": "Graphic Design", "skill_type": "teach"},
        {"student_id": 3, "student": "Ishaan", "skill_name": "Python", "skill_type": "learn"},
    ]
    for match in rank_matches(sample_students[0], sample_skills):
        print(
            f"{match['student']} | score {match['score']}/100; "
            f"teaches you: {', '.join(match['skills_they_teach']) or 'none'}; "
            f"learns from you: {', '.join(match['skills_you_teach']) or 'none'}"
        )


if __name__ == "__main__":
    main()

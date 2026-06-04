from sqlalchemy.orm import Session

from app.models import ApprovalLog, ApprovedResource, CandidateResource, Course, Topic, User
from app.utils import dumps


DEMO_COURSE_CODE = "DEMO-CSC415"


DEMO_TOPICS = [
    {
        "module_number": 1,
        "module_title": "Foundations of Artificial Intelligence",
        "week_number": 1,
        "topic_title": "Introduction to Artificial Intelligence",
        "subtopics": ["AI history", "intelligent agents", "problem domains"],
        "outcomes": ["Explain the scope and application areas of artificial intelligence."],
    },
    {
        "module_number": 2,
        "module_title": "Search and Problem Solving",
        "week_number": 3,
        "topic_title": "Uninformed and Informed Search",
        "subtopics": ["breadth-first search", "depth-first search", "A* search"],
        "outcomes": ["Compare search strategies for solving AI problems."],
    },
    {
        "module_number": 3,
        "module_title": "Machine Learning Foundations",
        "week_number": 6,
        "topic_title": "Supervised Machine Learning",
        "subtopics": ["classification", "regression", "model evaluation"],
        "outcomes": ["Describe how supervised learning models are trained and evaluated."],
    },
]


DEMO_CANDIDATES = {
    "Introduction to Artificial Intelligence": [
        ("Books", "Artificial Intelligence: A Modern Approach", ["Stuart Russell", "Peter Norvig"], 2021, "https://aima.cs.berkeley.edu/"),
        ("Journal Articles", "Computing Machinery and Intelligence", ["Alan M. Turing"], 1950, "https://doi.org/10.1093/mind/LIX.236.433"),
        ("Industry Reports", "The AI Index Report", ["Stanford HAI"], 2024, "https://aiindex.stanford.edu/report/"),
        ("Newspaper Articles", "How artificial intelligence is changing education", ["The Conversation"], 2024, "https://theconversation.com/"),
        ("Software & Tools", "Google Teachable Machine", ["Google Creative Lab"], 2024, "https://teachablemachine.withgoogle.com/"),
    ],
    "Uninformed and Informed Search": [
        ("Books", "Artificial Intelligence: Foundations of Computational Agents", ["David L. Poole", "Alan K. Mackworth"], 2023, "https://artint.info/"),
        ("Journal Articles", "A Formal Basis for the Heuristic Determination of Minimum Cost Paths", ["Peter E. Hart", "Nils J. Nilsson", "Bertram Raphael"], 1968, "https://doi.org/10.1109/TSSC.1968.300136"),
        ("Workshops & Trainings", "CS50 AI Search Lecture", ["Harvard CS50"], 2024, "https://cs50.harvard.edu/ai/"),
        ("Software & Tools", "NetworkX Shortest Path Algorithms", ["NetworkX Developers"], 2024, "https://networkx.org/"),
        ("Industry Reports", "AI search and optimization applications", ["McKinsey & Company"], 2023, "https://www.mckinsey.com/"),
    ],
    "Supervised Machine Learning": [
        ("Books", "Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow", ["Aurelien Geron"], 2022, "https://www.oreilly.com/"),
        ("Journal Articles", "Random Forests", ["Leo Breiman"], 2001, "https://doi.org/10.1023/A:1010933404324"),
        ("Software & Tools", "Scikit-learn User Guide", ["Scikit-learn Developers"], 2024, "https://scikit-learn.org/stable/user_guide.html"),
        ("Workshops & Trainings", "Machine Learning Crash Course", ["Google"], 2024, "https://developers.google.com/machine-learning/crash-course"),
        ("Industry Reports", "State of AI in the Enterprise", ["Deloitte"], 2024, "https://www2.deloitte.com/"),
    ],
}


def seed_demo_data(db: Session) -> None:
    existing = db.query(Course).filter(Course.course_code == DEMO_COURSE_CODE).first()
    if existing:
        return

    admin = db.query(User).filter(User.role == "super_admin").order_by(User.id.asc()).first()
    course = Course(
        course_code=DEMO_COURSE_CODE,
        course_title="Artificial Intelligence Demo Course",
        college="College of Science and Technology",
        department="Computer and Information Sciences",
        programme="Computer Science",
        level="400",
        semester="Alpha Semester",
        session="2025/2026",
        lecturers_json=dumps(["Demo Lecturer"]),
        description="Demo course generated for final-year project presentation and workflow testing.",
        status="resources_generated",
        uploaded_by_id=admin.id if admin else None,
    )
    db.add(course)
    db.commit()
    db.refresh(course)

    topic_by_title: dict[str, Topic] = {}
    for item in DEMO_TOPICS:
        topic = Topic(
            course_id=course.id,
            module_number=item["module_number"],
            module_title=item["module_title"],
            week_number=item["week_number"],
            topic_title=item["topic_title"],
            subtopics_json=dumps(item["subtopics"]),
            outcomes_json=dumps(item["outcomes"]),
            extraction_confidence=0.92,
            is_searchable=True,
        )
        db.add(topic)
        db.commit()
        db.refresh(topic)
        topic_by_title[topic.topic_title] = topic

    approved_titles = {
        "Artificial Intelligence: A Modern Approach",
        "A Formal Basis for the Heuristic Determination of Minimum Cost Paths",
        "Scikit-learn User Guide",
    }
    for topic_title, rows in DEMO_CANDIDATES.items():
        topic = topic_by_title[topic_title]
        for index, (category, title, authors, year, url) in enumerate(rows, start=1):
            candidate = CandidateResource(
                course_id=course.id,
                topic_id=topic.id,
                category=category,
                title=title,
                authors_json=dumps(authors),
                year=year,
                abstract=f"Demo candidate resource for {topic_title}.",
                url=url,
                source_system="demo_seed",
                relevance_score=round(0.98 - (index * 0.04), 2),
                match_reason=f"Included as a strong {category.lower()} match for {topic_title}.",
                status="approved" if title in approved_titles else "pending",
            )
            db.add(candidate)
            db.commit()
            db.refresh(candidate)
            if title in approved_titles:
                db.add(
                    ApprovedResource(
                        course_id=course.id,
                        topic_id=topic.id,
                        candidate_id=candidate.id,
                        category=category,
                        title=title,
                        authors_json=dumps(authors),
                        year=year,
                        url=url,
                        source_system="demo_seed",
                        note="Pre-approved demo resource.",
                        approved_by_id=admin.id if admin else None,
                    )
                )
    db.add(
        ApprovalLog(
            actor_id=admin.id if admin else None,
            action="demo_data_seeded",
            entity_type="course",
            entity_id=course.id,
            after_json=dumps({"course_code": DEMO_COURSE_CODE, "topics": len(DEMO_TOPICS), "candidates": 15}),
        )
    )
    db.commit()

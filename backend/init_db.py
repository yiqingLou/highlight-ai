"""
Initialize the SQLite database for highlight-ai.

Run with: python init_db.py

This script:
1. Creates the database file (backend/highlight_ai.db)
2. Creates all 6 tables based on the ORM models
3. Inserts seed data: 5 BGM tracks + 7 default settings
4. Inserts a sample task with 3 highlights for testing

Safe to run multiple times - drops and recreates tables.
"""

from app.database import Base, engine, SessionLocal
from app.models import Task, Highlight, Clip, Bgm, Subtitle, Setting


def init_database():
    print("==> Dropping all existing tables (if any)...")
    Base.metadata.drop_all(bind=engine)

    print("==> Creating all 6 tables...")
    Base.metadata.create_all(bind=engine)
    print("    OK: 6 tables created")

    db = SessionLocal()

    try:
        # ============================================
        # Seed 1: BGM library (5 tracks)
        # ============================================
        print("==> Seeding BGM library (5 tracks)...")
        bgm_data = [
            Bgm(id=1, name="Epic Symphony", file_path="assets/bgm/epic_01.mp3",
                style="epic", duration_sec=204, license="CC0", sort_order=1),
            Bgm(id=2, name="Electronic Beat", file_path="assets/bgm/epic_02.mp3",
                style="epic", duration_sec=168, license="CC0", sort_order=2),
            Bgm(id=3, name="Hip Hop Groove", file_path="assets/bgm/funny_01.mp3",
                style="funny", duration_sec=192, license="YouTube Audio Lib", sort_order=3),
            Bgm(id=4, name="Tense Drums", file_path="assets/bgm/intense_01.mp3",
                style="intense", duration_sec=150, license="CC0", sort_order=4),
            Bgm(id=5, name="Cinematic Build", file_path="assets/bgm/cinematic_01.mp3",
                style="cinematic", duration_sec=240, license="CC0", sort_order=5),
        ]
        db.add_all(bgm_data)
        db.commit()
        print(f"    OK: {len(bgm_data)} BGM tracks inserted")

        # ============================================
        # Seed 2: Default settings (7 keys)
        # ============================================
        print("==> Seeding default settings (7 keys)...")
        settings_data = [
            Setting(key="default_aspect_ratio", value="16:9"),
            Setting(key="default_resolution", value="1080p"),
            Setting(key="default_bgm_style", value="epic"),
            Setting(key="primary_game", value="naraka"),
            Setting(key="auto_subtitle", value="true"),
            Setting(key="use_gpu", value="true"),
            Setting(key="output_dir", value="~/Videos/HighlightAI/"),
        ]
        db.add_all(settings_data)
        db.commit()
        print(f"    OK: {len(settings_data)} settings inserted")

        # ============================================
        # Seed 3: Sample task (1 task with 5 highlights)
        # ============================================
        print("==> Seeding sample task with 5 highlights...")
        sample_task = Task(
            id=1,
            file_path="C:\\Users\\21465\\videos\\naraka_demo.mp4",
            file_name="naraka_demo.mp4",
            file_size=2_500_000_000,
            duration_sec=3600.0,
            width=1920,
            height=1080,
            fps=60.0,
            game_type="naraka",
            status="done",
            progress=100,
        )
        db.add(sample_task)
        db.commit()
        print(f"    OK: 1 sample task created (id={sample_task.id})")

        highlights_data = [
            Highlight(task_id=1, start_sec=15.3, end_sec=23.1, score=92,
                      score_ocr=95, score_audio=88, score_visual=90,
                      label="Quintuple Kill",
                      reason="Triple kill + teammate cheer + visual burst",
                      is_selected=True, sort_order=1),
            Highlight(task_id=1, start_sec=754.2, end_sec=762.8, score=88,
                      score_ocr=85, score_audio=92, score_visual=85,
                      label="Clutch Comeback",
                      reason="1v3 outplay with low HP",
                      is_selected=True, sort_order=2),
            Highlight(task_id=1, start_sec=1691.4, end_sec=1699.9, score=81,
                      score_ocr=80, score_audio=78, score_visual=85,
                      label="Team Save",
                      reason="Pulled teammates from danger",
                      is_selected=True, sort_order=3),
            Highlight(task_id=1, start_sec=2700.0, end_sec=2708.5, score=65,
                      score_ocr=40, score_audio=85, score_visual=70,
                      label="Funny Fails",
                      reason="Teammate accidentally falls",
                      is_selected=False, sort_order=4),
            Highlight(task_id=1, start_sec=3510.7, end_sec=3518.2, score=79,
                      score_ocr=82, score_audio=75, score_visual=80,
                      label="Slick Play",
                      reason="Smooth movement combo",
                      is_selected=True, sort_order=5),
        ]
        db.add_all(highlights_data)
        db.commit()
        print(f"    OK: {len(highlights_data)} highlights inserted")

        # ============================================
        # Verification: count rows in each table
        # ============================================
        print("\n==> Verification - row counts:")
        print(f"    tasks:      {db.query(Task).count()}")
        print(f"    highlights: {db.query(Highlight).count()}")
        print(f"    clips:      {db.query(Clip).count()}")
        print(f"    bgm:        {db.query(Bgm).count()}")
        print(f"    subtitles:  {db.query(Subtitle).count()}")
        print(f"    settings:   {db.query(Setting).count()}")

        print("\n==> Database initialized successfully!")
        print(f"==> Database file: backend/highlight_ai.db")

    except Exception as e:
        print(f"ERROR: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_database()
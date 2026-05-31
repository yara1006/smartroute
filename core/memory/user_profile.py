from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

from core.models import UserProfile


class UserProfileManager:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("USER_DB_PATH", "./data/user_profiles.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS route_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    route_id TEXT,
                    route_data TEXT,
                    feedback INTEGER,
                    created_at TEXT
                )
                """
            )
            conn.commit()

    def get_profile(self, user_id: str) -> UserProfile:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT data FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            profile = UserProfile(user_id=user_id)
            self.save_profile(profile)
            return profile
        return UserProfile(**json.loads(row[0]))

    def save_profile(self, profile: UserProfile) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        data = profile.model_dump_json()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE
                SET data = excluded.data, updated_at = excluded.updated_at
                """,
                (profile.user_id, data, now, now),
            )
            conn.commit()

    def infer_profile_from_chat(self, user_id: str, extracted_preferences: dict) -> None:
        profile = self.get_profile(user_id)
        style = extracted_preferences.get("travel_style")
        if style and style != "休闲":
            profile.travel_style = style
        self.save_profile(profile)

    def update_from_route(self, user_id: str, route_data: dict, feedback: int = 0) -> None:
        profile = self.get_profile(user_id)
        for stop in route_data.get("stops", []):
            poi = stop.get("poi", {})
            poi_id = poi.get("id")
            category = poi.get("category")
            if not poi_id:
                continue
            if poi_id not in profile.visited_poi_ids:
                profile.visited_poi_ids.append(poi_id)
            if feedback == 1:
                if poi_id not in profile.liked_poi_ids:
                    profile.liked_poi_ids.append(poi_id)
                if category and category not in profile.preferred_categories:
                    profile.preferred_categories.append(category)
            elif feedback == -1:
                if poi_id not in profile.disliked_poi_ids:
                    profile.disliked_poi_ids.append(poi_id)
                if category and category not in profile.disliked_categories:
                    profile.disliked_categories.append(category)

        route_id = route_data.get("id", "")
        if route_id and route_id not in profile.history_routes:
            profile.history_routes.append(route_id)
        self.save_profile(profile)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO route_history (user_id, route_id, route_data, feedback, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    route_id,
                    json.dumps(route_data, ensure_ascii=False, default=str),
                    feedback,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()

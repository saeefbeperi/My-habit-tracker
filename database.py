import aiosqlite
from datetime import datetime, timedelta, timezone

from config import DB_PATH, STREAK_THRESHOLD


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(row)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


ALLOWED_USER_FIELDS = {"reminder_time", "summary_time", "timezone", "language"}

_TIME_SLOT_ORDER = {"Morning": 0, "Afternoon": 1, "Evening": 2, "Anytime": 3}


# ─────────────────────────────────────────────
# FEATURE 1 — init_db
# ─────────────────────────────────────────────

async def init_db() -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    first_name  TEXT NOT NULL,
                    reminder_time TEXT DEFAULT '08:00',
                    summary_time  TEXT DEFAULT '21:00',
                    timezone      TEXT DEFAULT 'Asia/Dhaka',
                    language      TEXT DEFAULT 'EN',
                    created_at    TEXT NOT NULL
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    task_name    TEXT NOT NULL,
                    planned_for  TEXT NOT NULL,
                    time_slot    TEXT DEFAULT 'Anytime',
                    status       TEXT DEFAULT 'pending',
                    completed_at TEXT,
                    created_at   TEXT NOT NULL
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS streaks (
                    user_id            INTEGER PRIMARY KEY,
                    current_streak     INTEGER DEFAULT 0,
                    longest_streak     INTEGER DEFAULT 0,
                    last_active_date   TEXT,
                    total_days_tracked INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_summaries (
                    summary_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id          INTEGER NOT NULL,
                    summary_date     TEXT NOT NULL,
                    total_tasks      INTEGER DEFAULT 0,
                    completed_tasks  INTEGER DEFAULT 0,
                    completion_rate  REAL DEFAULT 0.0,
                    summary_sent     INTEGER DEFAULT 0,
                    UNIQUE(user_id, summary_date)
                )
            """)

            await db.commit()
        print("✅ Database initialized")
    except Exception as e:
        print(f"[DB ERROR] init_db failed: {e}")
        raise


# ─────────────────────────────────────────────
# FEATURE 2 — get_or_create_user
# ─────────────────────────────────────────────

async def get_or_create_user(user_id: int, username: str, first_name: str) -> dict:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                print(f"[DB] User {user_id} ready")
                return _row_to_dict(row)

            now = _now_iso()
            await db.execute(
                """
                INSERT INTO users (user_id, username, first_name, reminder_time,
                                   summary_time, timezone, language, created_at)
                VALUES (?, ?, ?, '08:00', '21:00', 'Asia/Dhaka', 'EN', ?)
                """,
                (user_id, username, first_name, now),
            )
            await db.commit()

            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()

            print(f"[DB] User {user_id} ready")
            return _row_to_dict(row)
    except Exception as e:
        print(f"[DB ERROR] get_or_create_user({user_id}): {e}")
        raise


# ─────────────────────────────────────────────
# FEATURE 3 — get_user
# ─────────────────────────────────────────────

async def get_user(user_id: int) -> dict | None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
            return _row_to_dict(row) if row else None
    except Exception as e:
        print(f"[DB ERROR] get_user({user_id}): {e}")
        return None


# ─────────────────────────────────────────────
# FEATURE 4 — update_user_settings
# ─────────────────────────────────────────────

async def update_user_settings(user_id: int, field: str, value: str) -> None:
    if field not in ALLOWED_USER_FIELDS:
        raise ValueError(
            f"[DB] update_user_settings: field '{field}' is not allowed. "
            f"Allowed fields: {ALLOWED_USER_FIELDS}"
        )
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"UPDATE users SET {field} = ? WHERE user_id = ?",
                (value, user_id),
            )
            await db.commit()
    except Exception as e:
        print(f"[DB ERROR] update_user_settings({user_id}, {field}): {e}")
        raise


# ─────────────────────────────────────────────
# FEATURE 5 — add_task
# ─────────────────────────────────────────────

async def add_task(
    user_id: int,
    task_name: str,
    planned_for: str,
    time_slot: str = "Anytime",
) -> int:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            now = _now_iso()
            cursor = await db.execute(
                """
                INSERT INTO tasks (user_id, task_name, planned_for, time_slot,
                                   status, completed_at, created_at)
                VALUES (?, ?, ?, ?, 'pending', NULL, ?)
                """,
                (user_id, task_name, planned_for, time_slot, now),
            )
            await db.commit()
            task_id: int = cursor.lastrowid  # type: ignore[assignment]
            print(f"[DB] Task added for user {user_id}: {task_name}")
            return task_id
    except Exception as e:
        print(f"[DB ERROR] add_task({user_id}, {task_name!r}): {e}")
        raise


# ─────────────────────────────────────────────
# FEATURE 6 — get_tasks_for_date
# ─────────────────────────────────────────────

async def get_tasks_for_date(user_id: int, date_str: str) -> list[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM tasks
                WHERE user_id = ? AND planned_for = ?
                ORDER BY created_at ASC
                """,
                (user_id, date_str),
            ) as cursor:
                rows = await cursor.fetchall()

        tasks = [_row_to_dict(r) for r in rows]
        tasks.sort(
            key=lambda t: (
                _TIME_SLOT_ORDER.get(t.get("time_slot", "Anytime"), 3),
                t.get("created_at", ""),
            )
        )
        return tasks
    except Exception as e:
        print(f"[DB ERROR] get_tasks_for_date({user_id}, {date_str}): {e}")
        return []


# ─────────────────────────────────────────────
# FEATURE 7 — complete_task
# ─────────────────────────────────────────────

async def complete_task(task_id: int, user_id: int) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            now = _now_iso()
            cursor = await db.execute(
                """
                UPDATE tasks
                SET status = 'completed', completed_at = ?
                WHERE task_id = ? AND user_id = ? AND status = 'pending'
                """,
                (now, task_id, user_id),
            )
            await db.commit()
            success = cursor.rowcount > 0
            if success:
                print(f"[DB] Task {task_id} completed")
            return success
    except Exception as e:
        print(f"[DB ERROR] complete_task({task_id}, {user_id}): {e}")
        return False


# ─────────────────────────────────────────────
# FEATURE 8 — get_streak
# ─────────────────────────────────────────────

async def get_streak(user_id: int) -> dict:
    _default = {
        "user_id": user_id,
        "current_streak": 0,
        "longest_streak": 0,
        "last_active_date": None,
        "total_days_tracked": 0,
    }
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM streaks WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                return _row_to_dict(row)

            await db.execute(
                """
                INSERT OR IGNORE INTO streaks
                    (user_id, current_streak, longest_streak,
                     last_active_date, total_days_tracked)
                VALUES (?, 0, 0, NULL, 0)
                """,
                (user_id,),
            )
            await db.commit()
            return _default
    except Exception as e:
        print(f"[DB ERROR] get_streak({user_id}): {e}")
        return _default


# ─────────────────────────────────────────────
# FEATURE 9 — update_streak
# ─────────────────────────────────────────────

async def update_streak(user_id: int, date_str: str, completion_rate: float) -> dict:
    try:
        streak = await get_streak(user_id)

        current_streak: int = streak["current_streak"]
        longest_streak: int = streak["longest_streak"]
        last_active_date: str | None = streak["last_active_date"]
        total_days_tracked: int = streak["total_days_tracked"]

        if completion_rate >= STREAK_THRESHOLD:
            total_days_tracked += 1
            if last_active_date is not None:
                yesterday = (
                    datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)
                ).strftime("%Y-%m-%d")
                if last_active_date == yesterday:
                    current_streak += 1
                else:
                    current_streak = 1
            else:
                current_streak = 1

            if current_streak > longest_streak:
                longest_streak = current_streak

            new_last_active = date_str
        else:
            current_streak = 0
            new_last_active = last_active_date  # keep old value, don't advance

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO streaks
                    (user_id, current_streak, longest_streak,
                     last_active_date, total_days_tracked)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    current_streak     = excluded.current_streak,
                    longest_streak     = excluded.longest_streak,
                    last_active_date   = excluded.last_active_date,
                    total_days_tracked = excluded.total_days_tracked
                """,
                (user_id, current_streak, longest_streak, new_last_active, total_days_tracked),
            )
            await db.commit()

        return {
            "user_id": user_id,
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "last_active_date": new_last_active,
            "total_days_tracked": total_days_tracked,
        }
    except Exception as e:
        print(f"[DB ERROR] update_streak({user_id}, {date_str}): {e}")
        return await get_streak(user_id)


# ─────────────────────────────────────────────
# FEATURE 10 — get_stats
# ─────────────────────────────────────────────

async def get_stats(user_id: int) -> dict:
    try:
        streak = await get_streak(user_id)

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Total tasks ever
            async with db.execute(
                "SELECT COUNT(*) AS total FROM tasks WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                total_tasks_ever: int = row["total"] if row else 0

            # Completed tasks ever
            async with db.execute(
                "SELECT COUNT(*) AS completed FROM tasks WHERE user_id = ? AND status = 'completed'",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                completed_tasks_ever: int = row["completed"] if row else 0

            # Average completion rate from daily_summaries
            async with db.execute(
                "SELECT AVG(completion_rate) AS avg_rate FROM daily_summaries WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                avg_completion_rate: float = row["avg_rate"] if (row and row["avg_rate"] is not None) else 0.0

            # Last 7 days from daily_summaries
            async with db.execute(
                """
                SELECT summary_date AS date,
                       total_tasks AS total,
                       completed_tasks AS completed,
                       completion_rate AS rate
                FROM daily_summaries
                WHERE user_id = ?
                ORDER BY summary_date DESC
                LIMIT 7
                """,
                (user_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                last_7_days = [_row_to_dict(r) for r in rows]

        return {
            "current_streak": streak["current_streak"],
            "longest_streak": streak["longest_streak"],
            "last_active_date": streak["last_active_date"],
            "total_days_tracked": streak["total_days_tracked"],
            "total_tasks_ever": total_tasks_ever,
            "completed_tasks_ever": completed_tasks_ever,
            "avg_completion_rate": round(avg_completion_rate, 4),
            "last_7_days": last_7_days,
        }
    except Exception as e:
        print(f"[DB ERROR] get_stats({user_id}): {e}")
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "last_active_date": None,
            "total_days_tracked": 0,
            "total_tasks_ever": 0,
            "completed_tasks_ever": 0,
            "avg_completion_rate": 0.0,
            "last_7_days": [],
        }


# ─────────────────────────────────────────────
# FEATURE 11 — get_all_users
# ─────────────────────────────────────────────

async def get_all_users() -> list[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users") as cursor:
                rows = await cursor.fetchall()
            return [_row_to_dict(r) for r in rows]
    except Exception as e:
        print(f"[DB ERROR] get_all_users: {e}")
        return []


# ─────────────────────────────────────────────
# FEATURE 12 — save_daily_summary
# ─────────────────────────────────────────────

async def save_daily_summary(
    user_id: int,
    date_str: str,
    total: int,
    completed: int,
) -> None:
    try:
        rate = completed / total if total > 0 else 0.0
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO daily_summaries
                    (user_id, summary_date, total_tasks, completed_tasks,
                     completion_rate, summary_sent)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id, summary_date) DO UPDATE SET
                    total_tasks     = excluded.total_tasks,
                    completed_tasks = excluded.completed_tasks,
                    completion_rate = excluded.completion_rate,
                    summary_sent    = 1
                """,
                (user_id, date_str, total, completed, round(rate, 4)),
            )
            await db.commit()
    except Exception as e:
        print(f"[DB ERROR] save_daily_summary({user_id}, {date_str}): {e}")
        raise

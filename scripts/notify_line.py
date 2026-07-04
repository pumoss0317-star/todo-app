"""期限が近い・期限切れのTodoをLINEにブロードキャスト通知するスクリプト。
GitHub Actionsの定期実行から呼び出す想定（Streamlitアプリ本体とは独立して動作する）。
"""

import json
import os
import sys
from datetime import date, datetime

import gspread
import requests
from google.oauth2.service_account import Credentials

DUE_SOON_DAYS = 3
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def get_target_todos(sheet, target_email: str) -> list[dict]:
    records = sheet.get_all_records()
    today = date.today()
    result = []
    for record in records:
        if record.get("user_email") != target_email:
            continue
        if str(record.get("completed", "")).strip().upper() == "TRUE":
            continue
        due_date_str = record.get("due_date")
        if not due_date_str:
            continue
        try:
            due = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        diff = (due - today).days
        if diff > DUE_SOON_DAYS:
            continue
        result.append({**record, "_diff": diff})
    return sorted(result, key=lambda r: r["_diff"])


def format_message(todos: list[dict]) -> str:
    lines = ["【Todoリマインド】"]
    for todo in todos:
        diff = todo["_diff"]
        if diff < 0:
            status = f"⚠️ 期限切れ（{todo['due_date']}）"
        elif diff == 0:
            status = "⏰ 本日期限"
        else:
            status = f"⏰ あと{diff}日（{todo['due_date']}）"
        priority = f" [{todo['priority']}]" if todo.get("priority") else ""
        lines.append(f"・{todo['title']}{priority} {status}")
    return "\n".join(lines)


def send_line_broadcast(access_token: str, message: str) -> None:
    response = requests.post(
        LINE_BROADCAST_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"type": "text", "text": message}]},
        timeout=10,
    )
    response.raise_for_status()


def main() -> None:
    service_account_info = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    line_access_token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    target_email = os.environ["TODO_USER_EMAIL"]

    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(spreadsheet_id).sheet1

    todos = get_target_todos(sheet, target_email)
    if not todos:
        print("通知対象のTodoはありません。")
        return

    message = format_message(todos)
    send_line_broadcast(line_access_token, message)
    print(f"{len(todos)}件のTodoをLINEに通知しました。")


if __name__ == "__main__":
    sys.exit(main())

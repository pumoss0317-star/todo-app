import html
import uuid
from datetime import date, datetime, timedelta

import truststore

truststore.inject_into_ssl()

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

st.set_page_config(page_title="📝Todoアプリ", page_icon="✅")

if not st.user.is_logged_in:
    st.title("Todoアプリ")
    st.write("Googleアカウントでログインしてください。")
    if st.button("Googleでログイン"):
        st.login()
    st.stop()

st.sidebar.write(f"ログイン中: {st.user.email}")
if st.sidebar.button("ログアウト"):
    st.logout()


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
]


@st.cache_resource
def get_credentials():
    return Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )


@st.cache_resource
def get_worksheet():
    gc = gspread.authorize(get_credentials())
    sh = gc.open_by_key(st.secrets["sheets"]["spreadsheet_id"])
    return sh.sheet1


REQUIRED_COLUMNS = [
    "id",
    "user_email",
    "title",
    "content",
    "due_date",
    "updated_at",
    "completed",
    "created_at",
    "priority",
    "category",
    "calendar_event_id",
]


@st.cache_resource
def ensure_schema(_worksheet):
    headers = _worksheet.row_values(1)
    for name in REQUIRED_COLUMNS:
        if name not in headers:
            headers.append(name)
            _worksheet.update_cell(1, len(headers), name)
    return True


@st.cache_resource
def get_calendar_service():
    return build("calendar", "v3", credentials=get_credentials())


def get_calendar_id() -> str | None:
    return st.secrets.get("calendar", {}).get("calendar_id")


def create_calendar_event(title: str, content: str, due_date_str: str) -> str:
    calendar_id = get_calendar_id()
    if not calendar_id or not due_date_str:
        return ""
    try:
        due = datetime.strptime(due_date_str, "%Y-%m-%d").date()
    except ValueError:
        return ""
    body = {
        "summary": title,
        "description": content,
        "start": {"date": due_date_str},
        "end": {"date": (due + timedelta(days=1)).isoformat()},
    }
    try:
        event = (
            get_calendar_service()
            .events()
            .insert(calendarId=calendar_id, body=body)
            .execute()
        )
        return event["id"]
    except HttpError:
        st.warning("Googleカレンダーへの登録に失敗しました。")
        return ""


def update_calendar_event(
    event_id: str, title: str, content: str, due_date_str: str
) -> str:
    calendar_id = get_calendar_id()
    if not calendar_id:
        return event_id
    if not event_id:
        return create_calendar_event(title, content, due_date_str)
    if not due_date_str:
        delete_calendar_event(event_id)
        return ""
    try:
        due = datetime.strptime(due_date_str, "%Y-%m-%d").date()
    except ValueError:
        return event_id
    body = {
        "summary": title,
        "description": content,
        "start": {"date": due_date_str},
        "end": {"date": (due + timedelta(days=1)).isoformat()},
    }
    try:
        get_calendar_service().events().patch(
            calendarId=calendar_id, eventId=event_id, body=body
        ).execute()
        return event_id
    except HttpError:
        st.warning("Googleカレンダーの更新に失敗しました。")
        return event_id


def delete_calendar_event(event_id: str) -> None:
    calendar_id = get_calendar_id()
    if not calendar_id or not event_id:
        return
    try:
        get_calendar_service().events().delete(
            calendarId=calendar_id, eventId=event_id
        ).execute()
    except HttpError:
        pass


worksheet = get_worksheet()
ensure_schema(worksheet)
user_email = st.user.email

st.title("📝Todoアプリ")

if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
if "confirm_delete_id" not in st.session_state:
    st.session_state.confirm_delete_id = None


def get_my_todos() -> list[dict]:
    records = worksheet.get_all_records()
    return [r for r in records if r.get("user_email") == user_email]


def find_row_by_id(todo_id: str) -> int | None:
    cell = worksheet.find(todo_id, in_column=1)
    return cell.row if cell else None


def is_completed(todo: dict) -> bool:
    return str(todo.get("completed", "")).strip().upper() == "TRUE"


DUE_SOON_DAYS = 3

PRIORITY_OPTIONS = ["高", "中", "低"]
PRIORITY_ORDER = {"高": 0, "中": 1, "低": 2}
PRIORITY_ICON = {"高": "🔴", "中": "🟡", "低": "🟢"}


def priority_label(priority: str) -> str:
    icon = PRIORITY_ICON.get(priority, "")
    return f"{icon} {priority}" if priority else ""


def format_due_date(due_date_str: str, completed: bool) -> str:
    if not due_date_str:
        return ""
    label = f"📅 期日 : {due_date_str}"
    if completed:
        return label
    try:
        due = datetime.strptime(due_date_str, "%Y-%m-%d").date()
    except ValueError:
        return label

    diff = (due - date.today()).days
    if diff < 0:
        return f":red[📅 期日 : ⚠️ {due_date_str}（期限切れ）]"
    if diff <= DUE_SOON_DAYS:
        return f":orange[📅 期日 : ⏰ {due_date_str}]"
    return f":blue[{label}]"


todos = get_my_todos()
editing_todo = None
if st.session_state.editing_id:
    editing_todo = next(
        (t for t in todos if t["id"] == st.session_state.editing_id), None
    )
is_editing = editing_todo is not None

# --- 登録・編集フォーム ---
st.subheader("編集" if is_editing else "新規登録")

with st.form("todo_form", clear_on_submit=not is_editing):
    title = st.text_input("タイトル", value=editing_todo["title"] if is_editing else "")
    content = st.text_area(
        "内容", value=editing_todo["content"] if is_editing else ""
    )

    default_date = date.today()
    if is_editing and editing_todo.get("due_date"):
        try:
            default_date = datetime.strptime(
                editing_todo["due_date"], "%Y-%m-%d"
            ).date()
        except ValueError:
            pass
    due_date = st.date_input("期日", value=default_date)

    default_priority = editing_todo.get("priority") if is_editing else "中"
    priority = st.selectbox(
        "重要度",
        PRIORITY_OPTIONS,
        index=PRIORITY_OPTIONS.index(default_priority)
        if default_priority in PRIORITY_OPTIONS
        else 1,
    )
    category = st.text_input(
        "カテゴリ", value=editing_todo.get("category", "") if is_editing else ""
    )

    submitted = st.form_submit_button("更新" if is_editing else "登録")

    if submitted:
        if not title:
            st.error("タイトルは必須です。")
        else:
            now = datetime.now().isoformat(timespec="seconds")
            due_date_str = due_date.isoformat()
            if is_editing:
                row = find_row_by_id(editing_todo["id"])
                if row:
                    event_id = update_calendar_event(
                        editing_todo.get("calendar_event_id", ""),
                        title,
                        content,
                        due_date_str,
                    )
                    worksheet.update(
                        f"A{row}:K{row}",
                        [
                            [
                                editing_todo["id"],
                                user_email,
                                title,
                                content,
                                due_date_str,
                                now,
                                "TRUE" if is_completed(editing_todo) else "FALSE",
                                editing_todo["created_at"],
                                priority,
                                category,
                                event_id,
                            ]
                        ],
                    )
                st.session_state.editing_id = None
            else:
                new_id = str(uuid.uuid4())
                event_id = create_calendar_event(title, content, due_date_str)
                worksheet.append_row(
                    [
                        new_id,
                        user_email,
                        title,
                        content,
                        due_date_str,
                        now,
                        "FALSE",
                        now,
                        priority,
                        category,
                        event_id,
                    ]
                )
            st.rerun()

if is_editing and st.button("編集をキャンセル"):
    st.session_state.editing_id = None
    st.rerun()

# --- 一覧 ---
st.subheader("Todo一覧")
todos = get_my_todos()

search_query = st.text_input("タイトル・内容で検索", placeholder="キーワードを入力")

filter_col1, filter_col2 = st.columns(2)
with filter_col1:
    categories = sorted({t["category"] for t in todos if t.get("category")})
    selected_categories = st.multiselect("カテゴリで絞り込み", categories)
with filter_col2:
    selected_priorities = st.multiselect("重要度で絞り込み", PRIORITY_OPTIONS)

if search_query:
    query = search_query.lower()
    todos = [
        t
        for t in todos
        if query in t.get("title", "").lower() or query in t.get("content", "").lower()
    ]
if selected_categories:
    todos = [t for t in todos if t.get("category") in selected_categories]
if selected_priorities:
    todos = [t for t in todos if t.get("priority") in selected_priorities]

todos_sorted = sorted(
    todos,
    key=lambda t: (
        t.get("due_date") or "9999-99-99",
        PRIORITY_ORDER.get(t.get("priority"), 1),
    ),
)
active_todos = [t for t in todos_sorted if not is_completed(t)]
completed_todos = [t for t in todos_sorted if is_completed(t)]


def format_created_at(created_at_str: str) -> str:
    if not created_at_str:
        return ""
    try:
        created_at = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return created_at_str
    return created_at.strftime("%Y-%m-%d %H:%M")


def render_title_html(title: str, completed: bool) -> str:
    escaped = html.escape(title)
    if completed:
        escaped = f"<s>{escaped}</s>"
    return f"<span style='font-size:1.2em; font-weight:700'>{escaped}</span>"


def render_todo_list(todo_list: list[dict]) -> None:
    if not todo_list:
        st.write("該当するTodoはありません。")
        return

    for todo in todo_list:
        completed = is_completed(todo)

        with st.container(border=True):
            content_col, button_col = st.columns([6, 1.6], vertical_alignment="center")

            with content_col:
                title_cols = st.columns([0.6, 9], vertical_alignment="center")
                checked = title_cols[0].checkbox(
                    "完了",
                    value=completed,
                    key=f"done_{todo['id']}",
                    label_visibility="collapsed",
                )
                if checked != completed:
                    row = find_row_by_id(todo["id"])
                    if row:
                        worksheet.update_cell(row, 7, "TRUE" if checked else "FALSE")
                        if checked:
                            delete_calendar_event(todo.get("calendar_event_id", ""))
                            worksheet.update_cell(row, 11, "")
                        else:
                            event_id = create_calendar_event(
                                todo["title"], todo["content"], todo["due_date"]
                            )
                            worksheet.update_cell(row, 11, event_id)
                    st.rerun()
                title_cols[1].markdown(
                    render_title_html(todo["title"], completed), unsafe_allow_html=True
                )

                st.write(todo["content"])
                meta_parts = [format_due_date(todo["due_date"], completed)]
                if todo.get("priority"):
                    meta_parts.append(priority_label(todo["priority"]))
                if todo.get("category"):
                    meta_parts.append(f"🏷️ {todo['category']}")
                st.markdown(" ｜ ".join(p for p in meta_parts if p))
                st.caption(f"登録日時 : {format_created_at(todo.get('created_at', ''))}")

            with button_col:
                if st.button(
                    "編集", key=f"edit_{todo['id']}", use_container_width=True
                ):
                    st.session_state.editing_id = todo["id"]
                    st.rerun()

                if st.session_state.confirm_delete_id == todo["id"]:
                    if st.button(
                        "削除する",
                        key=f"confirm_delete_{todo['id']}",
                        type="primary",
                        use_container_width=True,
                    ):
                        row = find_row_by_id(todo["id"])
                        if row:
                            delete_calendar_event(todo.get("calendar_event_id", ""))
                            worksheet.delete_rows(row)
                        st.session_state.confirm_delete_id = None
                        st.rerun()
                    if st.button(
                        "取消", key=f"cancel_delete_{todo['id']}", use_container_width=True
                    ):
                        st.session_state.confirm_delete_id = None
                        st.rerun()
                else:
                    if st.button(
                        "削除",
                        key=f"delete_{todo['id']}",
                        type="primary",
                        use_container_width=True,
                    ):
                        st.session_state.confirm_delete_id = todo["id"]
                        st.rerun()


tab_active, tab_completed = st.tabs(
    [f"未完了 ({len(active_todos)})", f"完了済み ({len(completed_todos)})"]
)
with tab_active:
    render_todo_list(active_todos)
with tab_completed:
    render_todo_list(completed_todos)

import html
import uuid
from datetime import date, datetime

import truststore

truststore.inject_into_ssl()

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

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


@st.cache_resource
def get_worksheet():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(st.secrets["sheets"]["spreadsheet_id"])
    return sh.sheet1


worksheet = get_worksheet()
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
                    worksheet.update(
                        f"A{row}:H{row}",
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
                            ]
                        ],
                    )
                st.session_state.editing_id = None
            else:
                new_id = str(uuid.uuid4())
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
                    ]
                )
            st.rerun()

if is_editing and st.button("編集をキャンセル"):
    st.session_state.editing_id = None
    st.rerun()

# --- 一覧 ---
st.subheader("Todo一覧")
todos = get_my_todos()
todos_sorted = sorted(todos, key=lambda t: t.get("due_date") or "9999-99-99")
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
                    "", value=completed, key=f"done_{todo['id']}"
                )
                if checked != completed:
                    row = find_row_by_id(todo["id"])
                    if row:
                        worksheet.update_cell(row, 7, "TRUE" if checked else "FALSE")
                    st.rerun()
                title_cols[1].markdown(
                    render_title_html(todo["title"], completed), unsafe_allow_html=True
                )

                st.write(todo["content"])
                st.markdown(format_due_date(todo["due_date"], completed))
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


import json
import os
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Company HR Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

DATA_FILE = Path(__file__).parent / "hcm_data(1).json"


# =========================================================
# PREMIUM UI
# =========================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: Inter, sans-serif;
}

.stApp {
    background: #f4f7fc;
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #101a32 0%, #1c3157 100%);
}

[data-testid="stSidebar"] * {
    color: #f1f5ff;
}

[data-testid="stSidebar"] hr {
    border-color: #344768;
}

/* Sidebar M8 chat: readable dark text on the light input surface */
[data-testid="stSidebar"] [data-testid="stChatInput"] textarea,
[data-testid="stSidebar"] [data-testid="stChatInput"] input,
[data-testid="stSidebar"] .stChatInput textarea {
    color: #172554 !important;
    -webkit-text-fill-color: #172554 !important;
    caret-color: #172554 !important;
    background: #ffffff !important;
}
[data-testid="stSidebar"] [data-testid="stChatInput"] textarea::placeholder,
[data-testid="stSidebar"] .stChatInput textarea::placeholder {
    color: #64748b !important;
    -webkit-text-fill-color: #64748b !important;
    opacity: 1 !important;
}

h1, h2, h3 {
    color: #172554;
    font-weight: 750;
}

.hero {
    background: linear-gradient(115deg, #172554, #334e9a, #635bdb);
    padding: 28px 30px;
    border-radius: 18px;
    color: white;
    margin-bottom: 24px;
    box-shadow: 0 10px 30px rgba(37, 55, 110, .12);
}

.hero h1 {
    color: white;
    font-size: 30px;
    margin: 0 0 8px 0;
}

.hero p {
    color: #e0e7ff;
    margin: 0;
    font-size: 14px;
}

.metric-card {
    background: white;
    border: 1px solid #e5eaf3;
    border-radius: 15px;
    padding: 20px;
    min-height: 125px;
    box-shadow: 0 5px 18px rgba(24, 36, 59, .035);
}

.metric-label {
    color: #64748b;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .5px;
    margin-bottom: 12px;
}

.metric-value {
    color: #172554;
    font-size: 26px;
    font-weight: 800;
    line-height: 1.25;
    overflow-wrap: anywhere;
}

.metric-note {
    color: #718096;
    font-size: 12px;
    margin-top: 9px;
}

.section-title {
    color: #1e293b;
    font-size: 20px;
    font-weight: 750;
    margin: 22px 0 12px 0;
}

.stButton button, .stDownloadButton button {
    border-radius: 9px;
    font-weight: 600;
}

div[data-testid="stDataFrame"] {
    border: 1px solid #e5eaf3;
    border-radius: 10px;
}

div[data-testid="stTabs"] button {
    font-weight: 600;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# LOAD DATA
# =========================================================

@st.cache_data
def load_data(file_path, modified_time):
    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    users = pd.DataFrame(raw.get("users", []))
    attendance = pd.DataFrame(raw.get("attendance", []))
    leaves = pd.DataFrame(raw.get("leaves", []))
    payroll = pd.DataFrame(raw.get("salary_records", []))

    # Exclude admin login account from employee statistics.
    if not users.empty and "role" in users.columns:
        users = users[
            users["role"].astype(str).str.lower() != "admin"
        ].copy()

    # Never expose credentials in the UI.
    users = users.drop(
        columns=["password", "password_hash"],
        errors="ignore"
    )

    defaults = {
        "users": [
            "username", "name", "email", "role",
            "department", "designation", "salary"
        ],
        "attendance": [
            "username", "date", "check_in", "check_out",
            "status", "hours"
        ],
        "leaves": [
            "username", "type", "start", "end",
            "reason", "status"
        ],
        "payroll": [
            "username", "month", "gross_salary",
            "deduction", "net_salary", "paid"
        ]
    }

    frames = {
        "users": users,
        "attendance": attendance,
        "leaves": leaves,
        "payroll": payroll
    }

    for key, columns in defaults.items():
        for column in columns:
            if column not in frames[key].columns:
                frames[key][column] = None

    users = frames["users"]
    attendance = frames["attendance"]
    leaves = frames["leaves"]
    payroll = frames["payroll"]

    # Normalize identifiers.
    for frame in [users, attendance, leaves, payroll]:
        frame["username"] = (
            frame["username"].astype("string").str.strip()
        )

    # Employee profile mapping.
    profile_columns = [
        "username", "name", "email", "department", "designation", "role"
    ]

    profiles = users[profile_columns].drop_duplicates(
        subset=["username"]
    )

    attendance = attendance.merge(
        profiles,
        on="username",
        how="left",
        suffixes=("", "_profile")
    )

    leaves = leaves.merge(
        profiles,
        on="username",
        how="left",
        suffixes=("", "_profile")
    )

    payroll = payroll.merge(
        profiles,
        on="username",
        how="left",
        suffixes=("", "_profile")
    )

    # Numeric columns.
    for frame, columns in [
        (users, ["salary"]),
        (attendance, ["hours"]),
        (payroll, ["gross_salary", "deduction", "net_salary"])
    ]:
        for column in columns:
            frame[column] = pd.to_numeric(
                frame[column], errors="coerce"
            ).fillna(0)

    # Dates.
    attendance["date"] = pd.to_datetime(
        attendance["date"], errors="coerce"
    )

    for column in ["start", "end"]:
        leaves[column] = pd.to_datetime(
            leaves[column], errors="coerce"
        )

    # Normalize payment status.
    payroll["paid"] = (
        payroll["paid"]
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "paid"])
    )

    return users, attendance, leaves, payroll


if not DATA_FILE.exists():
    st.error(
        "hcm_data(1).json nahi mili. Dono files ko same folder mein rakhein."
    )
    st.stop()

try:
    users, attendance, leaves, payroll = load_data(
        str(DATA_FILE),
        DATA_FILE.stat().st_mtime
    )
except Exception as error:
    st.error(f"Data load error: {error}")
    st.stop()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def money(value):
    try:
        return f"PKR {float(value):,.0f}"
    except (ValueError, TypeError):
        return "PKR 0"


def metric_card(label, value, note=""):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-note">{note}</div>
    </div>
    """, unsafe_allow_html=True)


def section_header(title, subtitle=None):
    st.markdown(
        f'<div class="section-title">{title}</div>',
        unsafe_allow_html=True
    )
    if subtitle:
        st.caption(subtitle)


def show_table(frame, height=350):
    if frame.empty:
        st.info("Is section mein koi record available nahi.")
    else:
        st.dataframe(
            frame,
            use_container_width=True,
            hide_index=True,
            height=height
        )


def csv_download(frame, filename, label="Download CSV"):
    st.download_button(
        label=label,
        data=frame.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True
    )


def chart_layout(fig, height=350):
    fig.update_layout(
        height=height,
        margin=dict(l=15, r=15, t=50, b=15),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="Inter, sans-serif", color="#475569"),
        title_font=dict(size=16, color="#1e293b"),
        legend_title_text=""
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#edf1f7", zeroline=False)
    return fig


def format_dates(frame, columns):
    frame = frame.copy()

    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_datetime(
                frame[column], errors="coerce"
            ).dt.strftime("%Y-%m-%d")

    return frame


def employee_columns(frame):
    columns = [
        "username", "name", "email", "department",
        "designation", "role", "salary"
    ]
    return [c for c in columns if c in frame.columns]


def scope_records(frame, employee_ids, all_company=False):
    if all_company:
        return frame.copy()

    if "username" not in frame.columns:
        return frame.iloc[0:0].copy()

    return frame[
        frame["username"].astype(str).isin(
            [str(x) for x in employee_ids]
        )
    ].copy()



# =========================================================
# PERSISTENT HR WORKFLOWS
# =========================================================

def read_raw_data():
    """Read the JSON afresh so HR changes are not hidden by cached analytics."""
    with open(DATA_FILE, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    raw.setdefault("rules", {})
    raw.setdefault("public_holidays", [])
    raw.setdefault("salary_structures", {})
    raw.setdefault("attendance_corrections", [])
    raw.setdefault("payroll_drafts", [])
    return raw


def save_raw_data(raw, message="Changes saved successfully."):
    """Persist HR changes in the existing company JSON file."""
    try:
        backup_path = DATA_FILE.with_suffix(".json.bak")
        if DATA_FILE.exists() and not backup_path.exists():
            backup_path.write_text(DATA_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        temp_path = DATA_FILE.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8"
        )
        temp_path.replace(DATA_FILE)
        st.cache_data.clear()
        st.success(message)
        st.rerun()
    except Exception as exc:
        st.error(f"Could not save data: {exc}")


def clean_text(value):
    return str(value or "").strip()


def employee_name(raw, username):
    for emp in raw.get("users", []):
        if str(emp.get("username", "")) == str(username):
            return emp.get("name") or username
    return username


def parse_csv_list(value, fallback):
    values = [item.strip() for item in str(value or "").split(",") if item.strip()]
    return values or fallback


def safe_number(value, default=0.0):
    try:
        number = float(value)
        return number if number >= 0 else default
    except (TypeError, ValueError):
        return default



# =========================================================
# AI ASSISTANT (M8) — model assists; JSON remains source of truth
# =========================================================
AI_TOOL_DEFS = [
 {"type":"function","function":{"name":"get_headcount","description":"Get employee headcount, optionally by department.","parameters":{"type":"object","properties":{"department":{"type":"string"}},"required":[]}}},
 {"type":"function","function":{"name":"get_attendance_summary","description":"Attendance status counts for a date (defaults today).","parameters":{"type":"object","properties":{"date":{"type":"string","description":"YYYY-MM-DD"}},"required":[]}}},
 {"type":"function","function":{"name":"get_late_comers","description":"List late employees for a date (defaults today).","parameters":{"type":"object","properties":{"date":{"type":"string"}},"required":[]}}},
 {"type":"function","function":{"name":"get_leave_summary","description":"Leave counts by status and type.","parameters":{"type":"object","properties":{"status":{"type":"string"}},"required":[]}}},
 {"type":"function","function":{"name":"get_my_leave_balance","description":"Get current user's yearly leave quota and used/remaining days.","parameters":{"type":"object","properties":{},"required":[]}}},
 {"type":"function","function":{"name":"get_payroll_summary","description":"Summarize payroll totals for month YYYY-MM (defaults current month).","parameters":{"type":"object","properties":{"month":{"type":"string"}},"required":[]}}},
 {"type":"function","function":{"name":"search_employees","description":"Search employee profiles by name, username, department or designation. Never return credentials.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}}
]


def _ai_current_user(raw):
    return str(st.session_state.get("ai_username", "admin"))


def _ai_role(raw, username):
    u = next((x for x in raw.get("users", []) if str(x.get("username")) == str(username)), {})
    return str(u.get("role", "employee")).lower(), u


def _ai_visible_employees(raw, username):
    role, current = _ai_role(raw, username)
    employees = [u for u in raw.get("users", []) if str(u.get("role", "")).lower() != "admin"]
    if role in ("admin", "hr"):
        return employees
    return [u for u in employees if str(u.get("username")) == username]


def _ai_call_tool(name, args, raw, username):
    role, current = _ai_role(raw, username)
    company_roles = role in ("admin", "hr")
    visible = _ai_visible_employees(raw, username)
    allowed_ids = {str(x.get("username")) for x in visible}
    users = raw.get("users", [])
    attendance = [x for x in raw.get("attendance", []) if str(x.get("username")) in allowed_ids]
    leaves = [x for x in raw.get("leaves", []) if str(x.get("username")) in allowed_ids]
    payroll = [x for x in raw.get("salary_records", []) if str(x.get("username")) in allowed_ids]
    today = str(date.today())
    if name == "get_headcount":
        dept = clean_text(args.get("department"))
        rows = [u for u in visible if not dept or clean_text(u.get("department")).lower()==dept.lower()]
        return {"headcount":len(rows), "department":dept or "all", "employees":[{"name":u.get("name"),"department":u.get("department")} for u in rows]}
    if name == "get_attendance_summary":
        d=clean_text(args.get("date")) or today; rows=[x for x in attendance if clean_text(x.get("date"))==d]
        return {"date":d,"records":len(rows),"status_counts":pd.Series([clean_text(x.get("status")).lower() or "unknown" for x in rows]).value_counts().to_dict()}
    if name == "get_late_comers":
        d=clean_text(args.get("date")) or today
        return {"date":d,"late_comers":[{"username":x.get("username"),"name":next((u.get("name") for u in visible if str(u.get("username"))==str(x.get("username"))),x.get("username")),"check_in":x.get("check_in")} for x in attendance if clean_text(x.get("date"))==d and clean_text(x.get("status")).lower()=="late"]}
    if name == "get_leave_summary":
        status=clean_text(args.get("status")).lower(); rows=[x for x in leaves if not status or clean_text(x.get("status")).lower()==status]
        return {"total":len(rows),"status_counts":pd.Series([clean_text(x.get("status")).lower() or "unknown" for x in rows]).value_counts().to_dict(),"type_counts":pd.Series([clean_text(x.get("type")).lower() or "unknown" for x in rows]).value_counts().to_dict()}
    if name == "get_my_leave_balance":
        quota=safe_number(raw.get("rules",{}).get("leave_quota",20)); mine=[x for x in raw.get("leaves",[]) if str(x.get("username"))==username and clean_text(x.get("status")).lower()=="approved"]
        used=0
        for x in mine:
            try: used += max(1,(date.fromisoformat(str(x.get("end"))[:10])-date.fromisoformat(str(x.get("start"))[:10])).days+1)
            except Exception: pass
        return {"username":username,"annual_quota_days":quota,"approved_leave_days_used":used,"remaining_days":max(0,quota-used)}
    if name == "get_payroll_summary":
        month=clean_text(args.get("month")) or date.today().strftime("%Y-%m"); rows=[x for x in payroll if clean_text(x.get("month"))==month]
        return {"month":month,"employees_paid_or_recorded":len(rows),"gross_total":sum(safe_number(x.get("gross_salary")) for x in rows),"deductions_total":sum(safe_number(x.get("deduction")) for x in rows),"net_total":sum(safe_number(x.get("net_salary")) for x in rows)}
    if name == "search_employees":
        q=clean_text(args.get("query")).lower(); found=[u for u in visible if q in " ".join(str(u.get(k,"")) for k in ("username","name","department","designation")).lower()]
        return [{k:u.get(k) for k in ("username","name","department","designation","email")} for u in found[:20]]
    return {"error":"Unknown tool"}


def _ai_api(messages, tools=None, json_mode=False):
    """Gemini generateContent adapter; returns an OpenAI-shaped response for existing UI code."""
    # Streamlit secrets may raise when no secrets.toml exists; environment variables remain supported.
    try:
        secrets = st.secrets
        secret_key = secrets.get("GEMINI_API_KEY", "")
        secret_model = secrets.get("GEMINI_MODEL", "")
        secret_base_url = secrets.get("GEMINI_BASE_URL", "")
    except Exception:
        secret_key = secret_model = secret_base_url = ""
    api_key = secret_key or os.getenv("GEMINI_API_KEY", "")
    model = secret_model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    base_url = (secret_base_url or os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")).rstrip("/")
    if not api_key:
        raise RuntimeError("Gemini API key missing. Add GEMINI_API_KEY to .streamlit/secrets.toml or set the GEMINI_API_KEY environment variable.")

    system_instruction = None
    contents = []
    pending_calls = {}
    for m in messages:
        role = m.get("role", "user")
        if role == "system":
            system_instruction = (system_instruction or "") + str(m.get("content", "")) + "\n"
        elif role == "tool":
            call_id = m.get("tool_call_id", "")
            call = pending_calls.get(call_id, {})
            fn_name = call.get("name", "unknown_tool")
            try: result_obj = json.loads(m.get("content", "{}"))
            except Exception: result_obj = {"result": m.get("content", "")}
            contents.append({"role":"user", "parts":[{"functionResponse":{"name":fn_name,"response":result_obj}}]})
        elif role == "assistant" and m.get("tool_calls"):
            parts=[]
            for tc in m["tool_calls"]:
                fn=tc.get("function",{}); call_id=tc.get("id",fn.get("name","call"))
                try: args=json.loads(fn.get("arguments") or "{}")
                except Exception: args={}
                pending_calls[call_id]={"name":fn.get("name","unknown_tool"),"args":args}
                parts.append({"functionCall":{"name":fn.get("name","unknown_tool"),"args":args}})
            contents.append({"role":"model","parts":parts})
        elif role == "assistant":
            contents.append({"role":"model","parts":[{"text":str(m.get("content") or "")}]})
        else:
            contents.append({"role":"user","parts":[{"text":str(m.get("content") or "")}]})

    payload={"contents":contents,"generationConfig":{"temperature":0.2}}
    if system_instruction: payload["systemInstruction"]={"parts":[{"text":system_instruction}]}
    if tools:
        declarations=[]
        for item in tools:
            fn=item.get("function",item)
            declarations.append({"name":fn["name"],"description":fn.get("description","") ,"parameters":fn.get("parameters",{"type":"object","properties":{}})})
        payload["tools"]=[{"functionDeclarations":declarations}]
        payload["toolConfig"]={"functionCallingConfig":{"mode":"AUTO"}}
    if json_mode:
        payload.setdefault("generationConfig",{}).update({"responseMimeType":"application/json"})

    url=f"{base_url}/models/{model}:generateContent?key={api_key}"
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=60) as response: data=json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        detail=e.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"Gemini API returned HTTP {e.code}: {detail}")
    candidate=(data.get("candidates") or [{}])[0]
    parts=(candidate.get("content") or {}).get("parts",[])
    text_content="\n".join(p.get("text","") for p in parts if p.get("text"))
    tool_calls=[]
    for i,part in enumerate(parts):
        fc=part.get("functionCall")
        if fc:
            tool_calls.append({"id":f"gemini_call_{len(tool_calls)}_{fc.get('name','tool')}","type":"function","function":{"name":fc.get("name",""),"arguments":json.dumps(fc.get("args",{}),ensure_ascii=False)}})
    msg={"role":"assistant","content":text_content or None}
    if tool_calls: msg["tool_calls"]=tool_calls
    return {"choices":[{"message":msg,"finish_reason":"tool_calls" if tool_calls else "stop"}]}


def ai_system_prompt(raw, role, username):
    rules=raw.get("rules",{})
    policy={k:v for k,v in rules.items() if k in ("office_start","office_end","grace_minutes","weekends","departments","designations","leave_types","leave_quota","public_holidays")}
    return ("You are M8, an HR assistant. Explain and assist; the company's JSON database is the sole source of truth. "
      "Use tools for company facts, never invent employee, attendance, leave, or payroll values. Respect user scope: employee can access only their own records; HR/admin may access company records. "
      "Policy Q&A must be answered only from this policy JSON; if missing, say you do not know and ask HR/admin. Never expose passwords, hashes, or secrets. "
      f"Current user={username}; role={role}. Policy JSON: {json.dumps(policy,default=str)}")


def render_ai_assistant(raw):
    st.markdown("### 🤖 M8 AI Assistant")
    st.caption("AI explains and assists. Company JSON data is the source of truth.")
    # No profile/access-scope selector in M8. Use company-wide HR assistant context.
    st.session_state["ai_username"] = "admin"
    username="admin"
    role="admin"
    if "ai_messages" not in st.session_state: st.session_state.ai_messages=[]
    for msg in st.session_state.ai_messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    prompt=st.chat_input("Ask HR data or company policy…",key="m8_chat_input")
    if prompt:
        st.session_state.ai_messages.append({"role":"user","content":prompt})
        with st.chat_message("user"): st.markdown(prompt)
        history=[{"role":"system","content":ai_system_prompt(raw,role,username)}]+st.session_state.ai_messages[-12:]
        try:
            with st.spinner("M8 is checking the authorized data…"):
                response=_ai_api(history,AI_TOOL_DEFS)
                msg=response["choices"][0]["message"]
                # Run only declared tool functions locally, after applying user scope.
                for _ in range(4):
                    calls=msg.get("tool_calls",[])
                    if not calls: break
                    history.append(msg)
                    for call in calls:
                        fn=call["function"]["name"]; args=json.loads(call["function"].get("arguments") or "{}")
                        result=_ai_call_tool(fn,args,raw,username)
                        history.append({"role":"tool","tool_call_id":call["id"],"content":json.dumps(result,default=str)})
                    response=_ai_api(history,AI_TOOL_DEFS); msg=response["choices"][0]["message"]
                answer=msg.get("content") or "I could not produce an answer from the available data."
        except Exception as exc: answer=f"M8 unavailable: {exc}"
        st.session_state.ai_messages.append({"role":"assistant","content":answer})
        with st.chat_message("assistant"): st.markdown(answer)


def render_smart_leave(raw):
    st.markdown("### ✨ Smart Leave Request")
    request=st.text_input("Describe your leave in natural language",placeholder="Need next Monday and Tuesday off for a wedding",key="smart_leave_prompt")
    if st.button("Draft leave request",key="smart_leave_draft") and request.strip():
        raw_rules=raw.get("rules",{}); username=_ai_current_user(raw); role,_=_ai_role(raw,username)
        system="Extract leave request only as JSON object with keys type,start,end,reason. Dates must be YYYY-MM-DD. Resolve relative dates from today. Use configured leave types: "+json.dumps(raw_rules.get("leave_types",[]),default=str)+". If details/date are unclear, set missing fields to empty string. Do not submit or approve."
        try:
            res=_ai_api([{"role":"system","content":system},{"role":"user","content":request}],json_mode=True)
            draft=json.loads(res["choices"][0]["message"].get("content") or "{}")
            st.session_state["smart_leave_draft_data"]=draft
        except Exception as exc: st.error(f"Could not draft leave: {exc}")
    draft=st.session_state.get("smart_leave_draft_data")
    if draft:
        types=raw.get("rules",{}).get("leave_types",[]) or ["Annual","Sick","Casual"]
        with st.form("smart_leave_confirm_form"):
            typ=st.selectbox("Leave type",types,index=types.index(draft.get("type")) if draft.get("type") in types else 0)
            c1,c2=st.columns(2)
            try: start_default=date.fromisoformat(draft.get("start",""))
            except Exception: start_default=date.today()+timedelta(days=1)
            try: end_default=date.fromisoformat(draft.get("end",""))
            except Exception: end_default=start_default
            start= c1.date_input("Start",value=start_default); end=c2.date_input("End",value=end_default)
            reason=st.text_area("Reason",value=draft.get("reason",""))
            confirm=st.form_submit_button("Confirm & Submit Leave",type="primary")
            if confirm:
                if end<start: st.error("End date start date se pehle nahi ho sakti.")
                else:
                    username=_ai_current_user(raw); role,_=_ai_role(raw,username)
                    raw.setdefault("leaves",[]).append({"username":username,"type":typ,"start":str(start),"end":str(end),"reason":reason.strip(),"status":"Pending","comment":""})
                    save_raw_data(raw,"Leave request submitted for HR review.")



def hero(title, subtitle):
    st.markdown(
        f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True
    )


def render_admin_controls():
    raw = read_raw_data()
    rules = raw.setdefault("rules", {})
    hero(
        "Admin Control System",
        "Configure office policy, departments, designations, leave quotas and public holidays."
    )

    tab_hours, tab_org, tab_leave, tab_holidays = st.tabs([
        "Office Policy", "Organization", "Leave Policies", "Public Holidays"
    ])

    with tab_hours:
        st.markdown("### Working hours & attendance policy")
        with st.form("office_policy_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                office_start = st.text_input(
                    "Office start (HH:MM)", value=str(rules.get("office_start", "09:00"))
                )
                office_end = st.text_input(
                    "Office closing (HH:MM)", value=str(rules.get("office_end", "18:00"))
                )
            with c2:
                grace = st.number_input(
                    "Grace time (minutes)", min_value=0, max_value=180,
                    value=int(safe_number(rules.get("grace_minutes", 10)))
                )
                lunch = st.number_input(
                    "Break time (minutes)", min_value=0, max_value=240,
                    value=int(safe_number(rules.get("break_minutes", 60)))
                )
            with c3:
                weekend_options = ["Monday", "Tuesday", "Wednesday", "Thursday",
                                   "Friday", "Saturday", "Sunday"]
                old_weekends = rules.get("weekends", ["Saturday", "Sunday"])
                weekends = st.multiselect(
                    "Weekly weekend days", weekend_options,
                    default=[x for x in old_weekends if x in weekend_options]
                )
                quota_default = int(safe_number(rules.get("leave_quota", 20)))
                st.caption(f"Legacy default leave quota: {quota_default} days")
            save_policy = st.form_submit_button("Save Office Policy", type="primary",
                                                use_container_width=True)
            if save_policy:
                try:
                    from datetime import time as _time
                    _time.fromisoformat(office_start)
                    _time.fromisoformat(office_end)
                    if office_start >= office_end:
                        st.error("Office closing time must be later than opening time.")
                    else:
                        rules.update({
                            "office_start": office_start,
                            "office_end": office_end,
                            "late_after": office_start,
                            "grace_minutes": int(grace),
                            "break_minutes": int(lunch),
                            "weekends": weekends
                        })
                        save_raw_data(raw, "Office policy saved.")
                except ValueError:
                    st.error("Time HH:MM format mein enter karein, for example 09:00.")

    with tab_org:
        st.markdown("### Departments & designations")
        existing_users = [u for u in raw.get("users", []) if str(u.get("role", "")).lower() != "admin"]
        current_departments = sorted({
            clean_text(u.get("department")) for u in existing_users if clean_text(u.get("department"))
        })
        current_designations = sorted({
            clean_text(u.get("designation")) for u in existing_users if clean_text(u.get("designation"))
        })
        c1, c2 = st.columns(2)
        with c1:
            dept_text = st.text_area(
                "Departments (comma-separated)",
                value=", ".join(rules.get("departments", current_departments or ["HR", "IT", "Finance", "Sales"])),
                height=110
            )
        with c2:
            designation_text = st.text_area(
                "Designations (comma-separated)",
                value=", ".join(rules.get("designations", current_designations or ["Manager", "Officer", "Executive"])),
                height=110
            )
        if st.button("Save Organization Lists", type="primary", key="save_org_lists"):
            rules["departments"] = parse_csv_list(dept_text, current_departments)
            rules["designations"] = parse_csv_list(designation_text, current_designations)
            save_raw_data(raw, "Departments and designations saved.")
        st.caption("These lists power the HR employee editor. Existing employee records are not automatically renamed.")

    with tab_leave:
        st.markdown("### Leave types & yearly quotas")
        leave_types = rules.get("leave_types", {
            "Annual": 14, "Casual": 10, "Sick": 8, "Unpaid": 0
        })
        if not isinstance(leave_types, dict):
            leave_types = {"Annual": 14, "Casual": 10, "Sick": 8, "Unpaid": 0}
        leave_df = pd.DataFrame([
            {"Leave Type": name, "Yearly Quota": int(safe_number(quota))}
            for name, quota in leave_types.items()
        ])
        edited_leave_df = st.data_editor(
            leave_df, num_rows="dynamic", hide_index=True, use_container_width=True,
            column_config={
                "Leave Type": st.column_config.TextColumn("Leave Type", required=True),
                "Yearly Quota": st.column_config.NumberColumn(
                    "Yearly Quota (days)", min_value=0, max_value=365, step=1, required=True
                )
            },
            key="leave_quota_editor"
        )
        if st.button("Save Leave Types & Quotas", type="primary"):
            updated = {}
            for _, row in edited_leave_df.iterrows():
                leave_name = clean_text(row.get("Leave Type"))
                if leave_name:
                    updated[leave_name] = int(safe_number(row.get("Yearly Quota")))
            if updated:
                rules["leave_types"] = updated
                rules["leave_quota"] = max(updated.values(), default=20)
                save_raw_data(raw, "Leave types and yearly quotas saved.")
            else:
                st.error("At least one leave type is required.")

    with tab_holidays:
        st.markdown("### Public holiday calendar")
        holidays = raw.get("public_holidays", [])
        if holidays:
            show_table(pd.DataFrame(holidays), 220)
        else:
            st.info("No public holidays configured yet.")
        with st.form("add_holiday_form", clear_on_submit=True):
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                holiday_date = st.date_input("Holiday date")
            with c2:
                holiday_name = st.text_input("Holiday name", placeholder="e.g. Independence Day")
            with c3:
                holiday_kind = st.selectbox("Category", ["Public", "Company", "Religious", "Other"])
            add_holiday = st.form_submit_button("Add Holiday", type="primary")
            if add_holiday:
                if not holiday_name.strip():
                    st.error("Holiday name is required.")
                elif any(h.get("date") == str(holiday_date) for h in holidays):
                    st.error("Is date par holiday already configured hai.")
                else:
                    holidays.append({
                        "date": str(holiday_date), "name": holiday_name.strip(),
                        "category": holiday_kind
                    })
                    holidays.sort(key=lambda h: h.get("date", ""))
                    save_raw_data(raw, "Public holiday added.")
        if holidays:
            labels = {
                f'{h.get("date", "")} — {h.get("name", "")}': i
                for i, h in enumerate(holidays)
            }
            selected_holiday = st.selectbox("Select holiday to remove", list(labels))
            if st.button("Delete Selected Holiday", key="delete_holiday"):
                raw["public_holidays"].pop(labels[selected_holiday])
                save_raw_data(raw, "Public holiday deleted.")


def render_hr_dashboard():
    raw = read_raw_data()
    hero(
        "HR Operations Dashboard",
        "Employee lifecycle, attendance corrections, leave approvals, salary structures and payroll drafts."
    )
    users_raw = raw.get("users", [])
    employees = [u for u in users_raw if str(u.get("role", "")).lower() != "admin"]
    employee_df = pd.DataFrame([
        {k: v for k, v in emp.items() if k not in ("password", "password_hash")}
        for emp in employees
    ])
    attendance_raw = raw.get("attendance", [])
    leaves_raw = raw.get("leaves", [])
    corrections = raw.get("attendance_corrections", [])
    salary_structures = raw.get("salary_structures", {})
    payroll_drafts = raw.get("payroll_drafts", [])

    pending_leaves = sum(str(x.get("status", "")).lower() == "pending" for x in leaves_raw)
    pending_corrections = sum(str(x.get("status", "Pending")).lower() == "pending" for x in corrections)
    late_count = sum(str(x.get("status", "")).lower() == "late" for x in attendance_raw)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("EMPLOYEES", f"{len(employees):,}", "Active employee profiles")
    with c2:
        metric_card("LATE ARRIVALS", f"{late_count:,}", "Recorded late attendance")
    with c3:
        metric_card("PENDING LEAVES", f"{pending_leaves:,}", "Waiting for HR decision")
    with c4:
        metric_card("CORRECTIONS", f"{pending_corrections:,}", "Pending attendance corrections")

    tab_emp, tab_salary, tab_att, tab_corr, tab_leave, tab_payroll, tab_insights = st.tabs([
        "Employee Register", "Salary Structures", "Daily Attendance",
        "Attendance Corrections", "Leave Approvals", "Monthly Payroll", "HR Insights"
    ])

    # Employee register: update one profile, optionally import CSV.
    with tab_emp:
        st.markdown("### Register & maintain employee records")
        sub_edit, sub_import = st.tabs(["Edit Employee", "CSV Import / Export"])
        with sub_edit:
            employee_ids = [str(u.get("username", "")) for u in employees if u.get("username")]
            if employee_ids:
                chosen = st.selectbox(
                    "Select employee", employee_ids,
                    format_func=lambda x: f"{employee_name(raw, x)} ({x})",
                    key="hr_edit_employee"
                )
                emp = next((u for u in users_raw if str(u.get("username", "")) == chosen), {})
                rules = raw.get("rules", {})
                departments = rules.get("departments", sorted({clean_text(u.get("department")) for u in employees if u.get("department")}))
                designations = rules.get("designations", sorted({clean_text(u.get("designation")) for u in employees if u.get("designation")}))
                with st.form("employee_profile_form"):
                    c1, c2 = st.columns(2)
                    with c1:
                        name = st.text_input("Full name", value=clean_text(emp.get("name")))
                        email = st.text_input("Email", value=clean_text(emp.get("email")))
                        department = st.selectbox(
                            "Department", list(dict.fromkeys(list(departments) + [clean_text(emp.get("department"))])),
                            index=(list(dict.fromkeys(list(departments) + [clean_text(emp.get("department"))])).index(clean_text(emp.get("department")))
                                   if clean_text(emp.get("department")) in list(dict.fromkeys(list(departments) + [clean_text(emp.get("department"))])) else 0)
                        )
                    with c2:
                        designation_options = list(dict.fromkeys(list(designations) + [clean_text(emp.get("designation"))]))
                        designation = st.selectbox(
                            "Designation", designation_options or ["Employee"],
                            index=designation_options.index(clean_text(emp.get("designation")))
                            if clean_text(emp.get("designation")) in designation_options else 0
                        )
                        role = st.selectbox(
                            "Role", ["employee", "hr", "manager"],
                            index=["employee", "hr", "manager"].index(str(emp.get("role", "employee")).lower())
                            if str(emp.get("role", "employee")).lower() in ["employee", "hr", "manager"] else 0
                        )
                        base_salary = st.number_input(
                            "Monthly basic salary (PKR)", min_value=0.0,
                            value=float(safe_number(emp.get("salary", 0))), step=1000.0
                        )
                    if st.form_submit_button("Save Employee Details", type="primary"):
                        emp.update({
                            "name": name.strip(), "email": email.strip(),
                            "department": department, "designation": designation,
                            "role": role, "salary": float(base_salary)
                        })
                        save_raw_data(raw, "Employee profile updated.")
            else:
                st.info("No employee profiles found.")
        with sub_import:
            st.caption("CSV columns supported: username, name, email, department, designation, role, salary. Existing usernames are updated; new usernames are added.")
            uploaded = st.file_uploader("Import employees CSV", type=["csv"], key="hr_employee_csv")
            if uploaded is not None:
                try:
                    import_df = pd.read_csv(uploaded).fillna("")
                    show_table(import_df.head(20))
                    if st.button("Apply CSV Import", type="primary"):
                        if "username" not in import_df.columns:
                            st.error("CSV mein username column lazmi hai.")
                        else:
                            by_id = {str(u.get("username", "")): u for u in users_raw}
                            changed = 0
                            allowed = {"name", "email", "department", "designation", "role", "salary"}
                            for _, row in import_df.iterrows():
                                uid = clean_text(row.get("username"))
                                if not uid or uid.lower() == "admin":
                                    continue
                                target = by_id.get(uid)
                                if target is None:
                                    target = {"username": uid, "role": "employee"}
                                    users_raw.append(target)
                                    by_id[uid] = target
                                for col in allowed:
                                    if col in import_df.columns and clean_text(row.get(col)) != "":
                                        target[col] = safe_number(row.get(col)) if col == "salary" else clean_text(row.get(col))
                                changed += 1
                            save_raw_data(raw, f"CSV import applied to {changed} employee row(s).")
                except Exception as exc:
                    st.error(f"CSV read error: {exc}")
            if not employee_df.empty:
                csv_download(employee_df, "employee_register.csv", "Export Employee Register")

    # Salary structure setup.
    with tab_salary:
        st.markdown("### Basic salary, allowances & deductions")
        ids = [str(u.get("username", "")) for u in employees if u.get("username")]
        if ids:
            chosen_salary_id = st.selectbox(
                "Employee", ids,
                format_func=lambda x: f"{employee_name(raw, x)} ({x})",
                key="salary_structure_employee"
            )
            emp = next(u for u in employees if str(u.get("username")) == chosen_salary_id)
            structure = salary_structures.get(chosen_salary_id, {})
            with st.form("salary_structure_form"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    basic = st.number_input(
                        "Basic salary (PKR)", min_value=0.0,
                        value=float(safe_number(structure.get("basic", emp.get("salary", 0))),),
                        step=1000.0
                    )
                    housing = st.number_input("Housing allowance", min_value=0.0,
                                              value=float(safe_number(structure.get("housing", 0))), step=500.0)
                with c2:
                    transport = st.number_input("Transport allowance", min_value=0.0,
                                                 value=float(safe_number(structure.get("transport", 0))), step=500.0)
                    medical = st.number_input("Medical allowance", min_value=0.0,
                                              value=float(safe_number(structure.get("medical", 0))), step=500.0)
                with c3:
                    other = st.number_input("Other allowances", min_value=0.0,
                                             value=float(safe_number(structure.get("other", 0))), step=500.0)
                    deduction = st.number_input("Monthly default deductions", min_value=0.0,
                                                value=float(safe_number(structure.get("deduction", 0))), step=500.0)
                st.metric("Estimated net monthly salary", money(basic + housing + transport + medical + other - deduction))
                if st.form_submit_button("Save Salary Structure", type="primary"):
                    salary_structures[chosen_salary_id] = {
                        "basic": basic, "housing": housing, "transport": transport,
                        "medical": medical, "other": other, "deduction": deduction,
                        "updated_at": pd.Timestamp.now().isoformat(timespec="seconds")
                    }
                    emp["salary"] = basic
                    save_raw_data(raw, "Salary structure saved.")

    # Daily attendance board.
    with tab_att:
        st.markdown("### Daily attendance board")
        att_df = pd.DataFrame(attendance_raw)
        if not att_df.empty:
            if "date" not in att_df.columns:
                att_df["date"] = ""
            att_df["date"] = pd.to_datetime(att_df["date"], errors="coerce")
            valid_dates = att_df["date"].dropna()
            selected_day = st.date_input(
                "Attendance date",
                value=(valid_dates.max().date() if not valid_dates.empty else pd.Timestamp.today().date()),
                key="hr_attendance_date"
            )
            day_df = att_df[att_df["date"].dt.date == selected_day].copy()
            if not day_df.empty:
                day_df["employee_name"] = day_df["username"].apply(lambda x: employee_name(raw, x))
                st.dataframe(day_df, use_container_width=True, hide_index=True)
                selected_att_index = st.selectbox(
                    "Choose attendance record to update",
                    day_df.index.tolist(),
                    format_func=lambda ix: f'{day_df.loc[ix, "username"]} · {day_df.loc[ix, "employee_name"]} · {day_df.loc[ix, "date"].date()}',
                    key="hr_att_record"
                )
                selected_att = attendance_raw[int(selected_att_index)]
                with st.form("attendance_update_form"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        check_in = st.text_input("Check-in (HH:MM)", value=clean_text(selected_att.get("check_in")))
                    with c2:
                        check_out = st.text_input("Check-out (HH:MM)", value=clean_text(selected_att.get("check_out")))
                    with c3:
                        status = st.selectbox(
                            "Attendance status",
                            ["Present", "Late", "Absent", "Half Day", "On Leave"],
                            index=(["Present", "Late", "Absent", "Half Day", "On Leave"].index(
                                clean_text(selected_att.get("status")).title())
                                if clean_text(selected_att.get("status")).title() in ["Present", "Late", "Absent", "Half Day", "On Leave"] else 0)
                        )
                    hours = st.number_input("Working hours", min_value=0.0, max_value=24.0,
                                            value=float(safe_number(selected_att.get("hours"))), step=0.5)
                    if st.form_submit_button("Save Attendance Record", type="primary"):
                        selected_att.update({"check_in": check_in.strip(), "check_out": check_out.strip(),
                                              "status": status, "hours": hours})
                        save_raw_data(raw, "Attendance record updated.")
            else:
                st.info("Selected date par attendance record nahi mila.")
        else:
            st.info("Attendance dataset empty hai.")

    # Correction approvals.
    with tab_corr:
        st.markdown("### Attendance correction requests")
        if not corrections:
            st.info("No correction requests yet. HR can review requests stored in attendance_corrections.")
        for i, request in enumerate(corrections):
            with st.expander(
                f'{request.get("username", "Employee")} · {request.get("date", "")} · {request.get("status", "Pending")}'
            ):
                st.write("**Employee:**", employee_name(raw, request.get("username", "")))
                st.write("**Requested correction:**", request.get("requested_change", ""))
                st.write("**Reason:**", request.get("reason", ""))
                st.write("**HR comment:**", request.get("comment", ""))
                if str(request.get("status", "Pending")).lower() == "pending":
                    decision = st.text_input("Decision comment", key=f"correction_comment_{i}")
                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button("Approve", key=f"correction_approve_{i}", type="primary"):
                            # Apply structured corrections to the matching attendance record.
                            for attendance_row in attendance_raw:
                                if (str(attendance_row.get("username", "")) == str(request.get("username", ""))
                                        and str(attendance_row.get("date", ""))[:10] == str(request.get("date", ""))[:10]):
                                    for field in ["check_in", "check_out"]:
                                        if clean_text(request.get(field)):
                                            attendance_row[field] = request[field]
                                    if clean_text(request.get("attendance_status")):
                                        attendance_row["status"] = request["attendance_status"]
                                    if request.get("hours") not in (None, ""):
                                        attendance_row["hours"] = safe_number(request.get("hours"))
                                    break
                            request.update({"status": "Approved", "comment": decision,
                                            "reviewed_at": pd.Timestamp.now().isoformat(timespec="seconds")})
                            save_raw_data(raw, "Attendance correction approved; matching attendance record updated when found.")
                    with a2:
                        if st.button("Reject", key=f"correction_reject_{i}"):
                            request.update({"status": "Rejected", "comment": decision,
                                            "reviewed_at": pd.Timestamp.now().isoformat(timespec="seconds")})
                            save_raw_data(raw, "Attendance correction rejected.")
        with st.expander("Create a correction request for an employee"):
            if employees:
                with st.form("create_correction_request"):
                    corr_id = st.selectbox("Employee", [str(e.get("username")) for e in employees], key="corr_employee")
                    corr_date = st.date_input("Correction date", key="corr_date")
                    requested_change = st.text_input("Requested change summary", placeholder="e.g. Correct check-in to 09:05")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        corr_check_in = st.text_input("Correct check-in (optional)", placeholder="09:05")
                    with c2:
                        corr_check_out = st.text_input("Correct check-out (optional)", placeholder="18:00")
                    with c3:
                        corr_status = st.selectbox("Correct status (optional)", ["No change", "Present", "Late", "Absent", "Half Day", "On Leave"])
                    corr_hours = st.number_input("Correct working hours (optional; 0 means no change)", min_value=0.0, max_value=24.0, value=0.0, step=0.5)
                    corr_reason = st.text_area("Reason")
                    if st.form_submit_button("Add Request"):
                        corrections.append({
                            "username": corr_id, "date": str(corr_date),
                            "requested_change": requested_change.strip(),
                            "check_in": corr_check_in.strip(),
                            "check_out": corr_check_out.strip(),
                            "attendance_status": "" if corr_status == "No change" else corr_status,
                            "hours": corr_hours if corr_hours > 0 else "",
                            "reason": corr_reason.strip(),
                            "status": "Pending", "comment": "",
                            "created_at": pd.Timestamp.now().isoformat(timespec="seconds")
                        })
                        save_raw_data(raw, "Attendance correction request added.")

    # Leave approvals with comments.
    with tab_leave:
        st.markdown("### Leave requests & HR decisions")
        if not leaves_raw:
            st.info("No leave requests available.")
        for i, leave in enumerate(leaves_raw):
            with st.expander(
                f'{leave.get("username", "")} · {leave.get("type", "Leave")} · {leave.get("start", "")} to {leave.get("end", "")} · {leave.get("status", "Pending")}'
            ):
                st.write("**Employee:**", employee_name(raw, leave.get("username", "")))
                st.write("**Reason:**", leave.get("reason", ""))
                st.write("**Current status:**", leave.get("status", "Pending"))
                st.write("**Existing comment:**", leave.get("hr_comment", leave.get("comment", "")))
                if str(leave.get("status", "")).lower() == "pending":
                    comment = st.text_area("HR decision comment", key=f"leave_comment_{i}")
                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button("Approve Leave", key=f"leave_approve_{i}", type="primary"):
                            leave.update({"status": "Approved", "hr_comment": comment,
                                          "reviewed_at": pd.Timestamp.now().isoformat(timespec="seconds")})
                            save_raw_data(raw, "Leave request approved.")
                    with a2:
                        if st.button("Reject Leave", key=f"leave_reject_{i}"):
                            if not comment.strip():
                                st.warning("Reject karne se pehle comment/reason enter karein.")
                            else:
                                leave.update({"status": "Rejected", "hr_comment": comment,
                                              "reviewed_at": pd.Timestamp.now().isoformat(timespec="seconds")})
                                save_raw_data(raw, "Leave request rejected.")

    # Monthly payroll draft: preview and save draft records; no bank/payment action.
    with tab_payroll:
        st.markdown("### Monthly payroll draft")
        payroll_month = st.text_input("Payroll month (YYYY-MM)", value=pd.Timestamp.today().strftime("%Y-%m"))
        if st.button("Generate / Refresh Payroll Draft", type="primary"):
            try:
                pd.Period(payroll_month, freq="M")
                draft_rows = []
                for emp in employees:
                    uid = str(emp.get("username", ""))
                    structure = salary_structures.get(uid, {})
                    basic_value = safe_number(structure.get("basic", emp.get("salary", 0)))
                    allowances = sum(safe_number(structure.get(k, 0)) for k in ["housing", "transport", "medical", "other"])
                    deductions_value = safe_number(structure.get("deduction", 0))
                    gross_value = basic_value + allowances
                    draft_rows.append({
                        "username": uid, "name": emp.get("name", uid),
                        "department": emp.get("department", "Unknown"),
                        "month": payroll_month, "basic_salary": basic_value,
                        "allowances": allowances, "gross_salary": gross_value,
                        "deduction": deductions_value, "net_salary": max(0, gross_value - deductions_value),
                        "status": "Draft"
                    })
                raw["payroll_drafts"] = [r for r in payroll_drafts if r.get("month") != payroll_month] + draft_rows
                save_raw_data(raw, f"Payroll draft generated for {payroll_month}.")
            except Exception:
                st.error("Month YYYY-MM format mein enter karein, for example 2026-10.")
        current_drafts = [r for r in payroll_drafts if r.get("month") == payroll_month]
        if current_drafts:
            draft_df = pd.DataFrame(current_drafts)
            show_table(draft_df, 400)
            total_gross = pd.to_numeric(draft_df.get("gross_salary", 0), errors="coerce").sum()
            total_net = pd.to_numeric(draft_df.get("net_salary", 0), errors="coerce").sum()
            c1, c2 = st.columns(2)
            with c1:
                metric_card("DRAFT GROSS PAYROLL", money(total_gross), payroll_month)
            with c2:
                metric_card("DRAFT NET PAYROLL", money(total_net), "Not yet paid")
            csv_download(draft_df, f"payroll_draft_{payroll_month}.csv", "Export Payroll Draft")
            if st.button("Mark Draft as Reviewed", key="review_payroll_draft"):
                for row in raw["payroll_drafts"]:
                    if row.get("month") == payroll_month:
                        row["status"] = "Reviewed"
                        row["reviewed_at"] = pd.Timestamp.now().isoformat(timespec="seconds")
                save_raw_data(raw, "Payroll draft marked as reviewed.")
        else:
            st.info("Is month ka payroll draft abhi generate nahi hua.")

    # Insights
    with tab_insights:
        st.markdown("### HR performance & workforce insights")
        att_df = pd.DataFrame(attendance_raw)
        leave_df = pd.DataFrame(leaves_raw)
        c1, c2, c3 = st.columns(3)
        late_n = sum(str(a.get("status", "")).lower() == "late" for a in attendance_raw)
        absent_n = sum(str(a.get("status", "")).lower() == "absent" for a in attendance_raw)
        approved_n = sum(str(l.get("status", "")).lower() == "approved" for l in leaves_raw)
        with c1:
            metric_card("LATE RECORDS", f"{late_n:,}", "All loaded attendance")
        with c2:
            metric_card("ABSENT RECORDS", f"{absent_n:,}", "All loaded attendance")
        with c3:
            metric_card("APPROVED LEAVES", f"{approved_n:,}", "Approved requests")
        g1, g2 = st.columns(2)
        with g1:
            if not att_df.empty and "status" in att_df:
                by_status = att_df["status"].fillna("Unknown").value_counts().rename_axis("Status").reset_index(name="Records")
                st.plotly_chart(chart_layout(px.bar(by_status, x="Status", y="Records", color="Status",
                                                     title="Attendance: late / absent / present")), use_container_width=True)
        with g2:
            if not leave_df.empty and "type" in leave_df:
                by_leave = leave_df.groupby("type").size().reset_index(name="Requests")
                st.plotly_chart(chart_layout(px.pie(by_leave, names="type", values="Requests", hole=.5,
                                                     title="Leave utilization by type")), use_container_width=True)
        if not employee_df.empty:
            dept_col = "department" if "department" in employee_df else None
            if dept_col:
                dept = employee_df.groupby(dept_col).size().reset_index(name="Employees")
                st.plotly_chart(chart_layout(px.bar(dept, x=dept_col, y="Employees", color=dept_col,
                                                     title="Employees by department")), use_container_width=True)


# =========================================================
# NAVIGATION
# =========================================================

with st.sidebar:
    st.markdown("""
    <div style="padding:15px 4px 22px;">
        <div style="font-size:12px;letter-spacing:2px;color:#93c5fd;">
            HCM Lite
        </div>
        <div style="font-size:25px;font-weight:800;margin-top:8px;">
            Company Dashboard
        </div>
        <div style="font-size:12px;color:#cbd5e1;margin-top:7px;">
            Human Capital Management
        </div>
        <div style="font-size:11px;color:#94a3b8;margin-top:5px;">
            For Admin, HR and Employees
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Pages are intentionally grouped in a clear workflow order.
    nav_options = [
        "Admin Dashboard",
        "HR Dashboard",
        "Dashboard Overview",
        "Find Employee",
        "Employee Database",
        "Attendance Record",
        "Leave History",
        "Payroll Analytics",
        "Data Export",
    ]

    selected_page = st.radio(
        "NAVIGATION",
        nav_options,
        label_visibility="visible"
    )

    st.divider()
    with st.expander("🤖 M8 AI Assistant", expanded=False):
        render_ai_assistant(read_raw_data())
    st.divider()
    st.caption("COMPANY ANALYTICS PLATFORM")


# =========================================================
# ADMIN DASHBOARD & HR OPERATIONS
# =========================================================

if selected_page == "HR Dashboard":
    render_hr_dashboard()

# =========================================================
# ADMIN DASHBOARD
# Admin Control System is now a tab inside this dashboard.
# =========================================================

elif selected_page == "Admin Dashboard":
    admin_overview_tab, admin_controls_tab = st.tabs([
        "Workforce Overview", "Admin Control System"
    ])

    with admin_controls_tab:
        render_admin_controls()

    with admin_overview_tab:
        st.markdown("""
        <div class="hero">
            <h1>Admin Control Center</h1>
            <p>Company-wide workforce intelligence, HR operations,
            attendance, leave management and payroll insights.</p>
        </div>
        """, unsafe_allow_html=True)

        # Scope filters.
        section_header("Analytics & Reporting Filters")

        f1, f2 = st.columns([1, 2])

        with f1:
            report_scope = st.selectbox(
                "Dashboard Scope",
                [
                    "All Company",
                    "HR Department",
                    "Specific Employee"
                ],
                key="admin_scope"
            )

        selected_employee_id = None

        employee_ids = (
            users["username"].dropna().astype(str).unique().tolist()
        )

        employee_labels = {}
        for _, emp in users.iterrows():
            emp_id = str(emp.get("username", ""))
            emp_name = str(emp.get("name", emp_id))
            employee_labels[emp_id] = f"{emp_name} ({emp_id})"

        with f2:
            if report_scope == "Specific Employee" and employee_ids:
                selected_employee_id = st.selectbox(
                    "Choose Employee",
                    employee_ids,
                    format_func=lambda x: employee_labels.get(x, x),
                    key="admin_employee"
                )
            elif report_scope == "HR Department":
                st.caption(
                    "HR employees will be identified using role and department fields."
                )
            else:
                st.caption("All available employee records are included.")

        # HR identification using role OR department.
        role_text = users["role"].fillna("").astype(str)
        dept_text = users["department"].fillna("").astype(str)

        hr_mask = (
            role_text.str.contains(
                r"\bhr\b|human resources", case=False, regex=True
            )
            | dept_text.str.contains(
                r"\bhr\b|human resources", case=False, regex=True
            )
        )

        if report_scope == "All Company":
            scoped_users = users.copy()
            all_company = True

        elif report_scope == "Specific Employee":
            scoped_users = users[
                users["username"].astype(str) == str(selected_employee_id)
            ].copy() if selected_employee_id else users.iloc[0:0].copy()
            all_company = False

        else:
            scoped_users = users[hr_mask].copy()
            all_company = False

        scoped_ids = (
            scoped_users["username"].dropna().astype(str).unique().tolist()
        )

        scoped_attendance = scope_records(
            attendance, scoped_ids, all_company
        )
        scoped_leaves = scope_records(
            leaves, scoped_ids, all_company
        )
        scoped_payroll = scope_records(
            payroll, scoped_ids, all_company
        )

        # KPI values.
        total_employees = len(scoped_users)
        total_attendance = len(scoped_attendance)
        total_leaves = len(scoped_leaves)
        net_payroll = scoped_payroll["net_salary"].sum()

        present_count = scoped_attendance["status"].astype(str).str.lower().isin(
            ["present", "on time"]
        ).sum()

        late_count = scoped_attendance["status"].astype(str).str.lower().eq(
            "late"
        ).sum()

        pending_leaves = scoped_leaves["status"].astype(str).str.lower().eq(
            "pending"
        ).sum()

        paid_amount = scoped_payroll.loc[
            scoped_payroll["paid"], "net_salary"
        ].sum()

        unpaid_amount = scoped_payroll.loc[
            ~scoped_payroll["paid"], "net_salary"
        ].sum()

        section_header("Executive Summary")

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            metric_card("TOTAL EMPLOYEES", f"{total_employees:,}", report_scope)
        with c2:
            metric_card("ATTENDANCE RECORDS", f"{total_attendance:,}",
                        f"{present_count:,} present/on time")
        with c3:
            metric_card("PENDING LEAVES", f"{pending_leaves:,}",
                        f"{total_leaves:,} total requests")
        with c4:
            metric_card("NET PAYROLL", money(net_payroll),
                        "Selected reporting scope")

        st.markdown("")

        c5, c6, c7, c8 = st.columns(4)

        with c5:
            department_count = (
                scoped_users["department"].nunique()
                if "department" in scoped_users.columns else 0
            )
            metric_card("DEPARTMENTS", f"{department_count:,}",
                        "Departments represented")
        with c6:
            metric_card("LATE ARRIVALS", f"{late_count:,}",
                        "Records marked late")
        with c7:
            metric_card("PAID PAYROLL", money(paid_amount),
                        "Recorded paid amount")
        with c8:
            metric_card("UNPAID PAYROLL", money(unpaid_amount),
                        "Recorded unpaid amount")

        st.markdown("---")
        section_header("Company Intelligence & Performance")

        chart1, chart2 = st.columns(2)

        with chart1:
            st.markdown("#### Workforce by Department")

            if not scoped_users.empty:
                dept_data = (
                    scoped_users.assign(
                        department=scoped_users["department"].fillna("Unknown")
                    )
                    .groupby("department")
                    .size()
                    .reset_index(name="Employees")
                    .sort_values("Employees", ascending=False)
                )

                fig = px.bar(
                    dept_data,
                    x="department",
                    y="Employees",
                    color="Employees",
                    text="Employees",
                    color_continuous_scale="Blues",
                    title="Employee Distribution"
                )
                fig.update_traces(textposition="outside")
                st.plotly_chart(chart_layout(fig), use_container_width=True)
            else:
                st.info("Employee data available nahi hai.")

        with chart2:
            st.markdown("#### Attendance Performance")

            if not scoped_attendance.empty:
                status_data = (
                    scoped_attendance["status"].fillna("Unknown")
                    .astype(str).value_counts()
                    .rename_axis("Status")
                    .reset_index(name="Records")
                )

                fig = px.pie(
                    status_data,
                    names="Status",
                    values="Records",
                    hole=0.58,
                    title="Attendance Status"
                )
                fig.update_traces(textinfo="label+percent")
                st.plotly_chart(chart_layout(fig), use_container_width=True)
            else:
                st.info("Attendance records available nahi hain.")

        chart3, chart4 = st.columns(2)

        with chart3:
            st.markdown("#### Leave Management")

            if not scoped_leaves.empty:
                leave_data = (
                    scoped_leaves["status"].fillna("Unknown")
                    .astype(str).value_counts()
                    .rename_axis("Status")
                    .reset_index(name="Requests")
                )

                fig = px.bar(
                    leave_data,
                    x="Status",
                    y="Requests",
                    color="Status",
                    text="Requests",
                    title="Leave Request Status"
                )
                fig.update_traces(textposition="outside")
                st.plotly_chart(chart_layout(fig), use_container_width=True)
            else:
                st.info("Leave records available nahi hain.")

        with chart4:
            st.markdown("#### Payroll Payment Status")

            payment_data = pd.DataFrame({
                "Status": ["Paid", "Unpaid"],
                "Amount": [paid_amount, unpaid_amount]
            })

            fig = px.pie(
                payment_data,
                names="Status",
                values="Amount",
                hole=0.58,
                title="Net Salary Distribution"
            )
            st.plotly_chart(chart_layout(fig), use_container_width=True)

        # Payroll comparison.
        section_header("Salary Expenditure by Department")

        if not scoped_payroll.empty:
            payroll_dept = (
                scoped_payroll.assign(
                    department=scoped_payroll["department"].fillna("Unknown")
                )
                .groupby("department", as_index=False)
                .agg(
                    Gross_Salary=("gross_salary", "sum"),
                    Deductions=("deduction", "sum"),
                    Net_Salary=("net_salary", "sum")
                )
            )

            fig = px.bar(
                payroll_dept,
                x="department",
                y=["Gross_Salary", "Deductions", "Net_Salary"],
                barmode="group",
                title="Gross Salary, Deductions and Net Salary"
            )
            fig.update_layout(yaxis_title="Amount (PKR)")
            st.plotly_chart(
                chart_layout(fig, 420),
                use_container_width=True
            )
        else:
            st.info("Payroll data available nahi hai.")

        # Detail tables.
        st.markdown("---")

        with st.expander("Employee Records", expanded=True):
            emp_cols = employee_columns(scoped_users)
            show_table(scoped_users[emp_cols], 300)
            csv_download(
                scoped_users[emp_cols],
                "admin_employee_records.csv",
                "Download Employee Records"
            )

        with st.expander("Attendance Records"):
            att_view = format_dates(scoped_attendance, ["date"])
            att_cols = [
                c for c in [
                    "username", "name", "department", "date",
                    "check_in", "check_out", "status", "hours"
                ] if c in att_view.columns
            ]
            show_table(att_view[att_cols], 300)
            csv_download(
                att_view[att_cols],
                "admin_attendance_records.csv",
                "Download Attendance Records"
            )

        with st.expander("Leave History"):
            leave_view = format_dates(scoped_leaves, ["start", "end"])
            leave_cols = [
                c for c in [
                    "username", "name", "department", "type",
                    "start", "end", "reason", "status"
                ] if c in leave_view.columns
            ]
            show_table(leave_view[leave_cols], 300)
            csv_download(
                leave_view[leave_cols],
                "admin_leave_records.csv",
                "Download Leave Records"
            )

        with st.expander("Payroll Records"):
            pay_view = scoped_payroll.copy()
            pay_view["Payment Status"] = pay_view["paid"].map({
                True: "Paid",
                False: "Unpaid"
            })

            pay_cols = [
                c for c in [
                    "username", "name", "department", "month",
                    "gross_salary", "deduction", "net_salary",
                    "Payment Status"
                ] if c in pay_view.columns
            ]
            show_table(pay_view[pay_cols], 300)
            csv_download(
                pay_view[pay_cols],
                "admin_payroll_records.csv",
                "Download Payroll Records"
            )


    # =========================================================
    # DASHBOARD OVERVIEW
    # =========================================================
elif selected_page == "Dashboard Overview":
    ai_raw_for_overview = read_raw_data()
    with st.expander("✨ Smart Leave Request", expanded=False):
        render_smart_leave(ai_raw_for_overview)
    with st.expander("🤖 M8 Dashboard Summary", expanded=False):
        if st.button("Summarize current dashboard KPIs", key="m8_dashboard_summary"):
            try:
                current_data = load_data(str(DATA_FILE), DATA_FILE.stat().st_mtime)
                kpis = {"employee_count":len(current_data["users"]),"attendance_records":len(current_data["attendance"]),"leave_records":len(current_data["leaves"]),"payroll_records":len(current_data["payroll"])}
                summary_response = _ai_api([{"role":"system","content":"Write 3-5 concise insight bullets using ONLY supplied KPI numbers. Do not infer trends, percentages, causes, or values not present. If data is insufficient, say so."},{"role":"user","content":json.dumps(kpis)}])
                st.markdown(summary_response["choices"][0]["message"].get("content","No summary returned."))
            except Exception as exc: st.error(f"Dashboard summary unavailable: {exc}")

    st.markdown("""
    <div class="hero">
        <h1>Dashboard Overview</h1>
        <p>Company workforce, attendance, leave and payroll at a glance.</p>
    </div>
    """, unsafe_allow_html=True)

    present = attendance["status"].astype(str).str.lower().isin(
        ["present", "on time"]
    ).sum()

    pending = leaves["status"].astype(str).str.lower().eq("pending").sum()

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        metric_card("TOTAL EMPLOYEES", f"{len(users):,}", "Employee profiles")
    with c2:
        metric_card("ATTENDANCE RECORDS", f"{len(attendance):,}",
                    f"{present:,} present/on time")
    with c3:
        metric_card("PENDING LEAVES", f"{pending:,}", "Awaiting decision")
    with c4:
        metric_card("NET PAYROLL", money(payroll["net_salary"].sum()),
                    "All payroll records")

    col1, col2 = st.columns(2)

    with col1:
        section_header("Employee Distribution")
        if not users.empty:
            data = users.assign(
                department=users["department"].fillna("Unknown")
            ).groupby("department").size().reset_index(name="Employees")

            fig = px.bar(
                data, x="department", y="Employees",
                color="Employees", text="Employees",
                title="Employees by Department"
            )
            st.plotly_chart(chart_layout(fig), use_container_width=True)

    with col2:
        section_header("Attendance Status")
        if not attendance.empty:
            data = attendance["status"].fillna("Unknown").value_counts()
            fig = px.pie(
                values=data.values,
                names=data.index,
                hole=.55,
                title="Attendance Overview"
            )
            st.plotly_chart(chart_layout(fig), use_container_width=True)

    section_header("Recent Attendance")
    recent = format_dates(attendance, ["date"]).sort_values(
        "date", ascending=False, na_position="last"
    )
    show_table(recent.head(10))


# =========================================================
# EMPLOYEE DATABASE
# =========================================================

elif selected_page == "Employee Database":

    st.markdown("""
    <div class="hero">
        <h1>Employee Database</h1>
        <p>Employee profiles and company directory.</p>
    </div>
    """, unsafe_allow_html=True)

    search = st.text_input(
        "Search employee",
        placeholder="Name, username, email, department..."
    )

    result = users.copy()

    if search.strip():
        mask = pd.Series(False, index=result.index)

        for col in [
            "username", "name", "email", "department", "designation"
        ]:
            if col in result.columns:
                mask |= result[col].fillna("").astype(str).str.contains(
                    search.strip(), case=False, regex=False
                )

        result = result[mask]

    emp_cols = employee_columns(result)
    show_table(result[emp_cols], 500)
    csv_download(result[emp_cols], "employee_database.csv")


# =========================================================
# ATTENDANCE RECORD
# =========================================================

elif selected_page == "Attendance Record":

    st.markdown("""
    <div class="hero">
        <h1>Attendance Record</h1>
        <p>Check-ins, check-outs, attendance status and working hours.</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        metric_card("TOTAL RECORDS", f"{len(attendance):,}", "Attendance entries")
    with c2:
        metric_card(
            "PRESENT",
            f"{attendance['status'].astype(str).str.lower().isin(['present', 'on time']).sum():,}",
            "Present/on time"
        )
    with c3:
        metric_card(
            "LATE ARRIVALS",
            f"{attendance['status'].astype(str).str.lower().eq('late').sum():,}",
            "Late records"
        )
    with c4:
        avg_hours = attendance["hours"].mean() if not attendance.empty else 0
        metric_card("AVERAGE HOURS", f"{avg_hours:.1f}", "Hours per record")

    col1, col2 = st.columns(2)

    with col1:
        status_data = attendance["status"].fillna("Unknown").value_counts()
        if not status_data.empty:
            fig = px.bar(
                x=status_data.index,
                y=status_data.values,
                labels={"x": "Status", "y": "Records"},
                title="Attendance Status"
            )
            st.plotly_chart(chart_layout(fig), use_container_width=True)

    with col2:
        if not attendance.empty:
            fig = px.histogram(
                attendance,
                x="hours",
                nbins=12,
                title="Working Hours Distribution"
            )
            st.plotly_chart(chart_layout(fig), use_container_width=True)

    view = format_dates(attendance, ["date"])
    cols = [
        c for c in [
            "username", "name", "department", "date",
            "check_in", "check_out", "status", "hours"
        ] if c in view.columns
    ]
    show_table(view[cols], 500)
    csv_download(view[cols], "attendance_records.csv")


# =========================================================
# LEAVE HISTORY
# =========================================================

elif selected_page == "Leave History":

    st.markdown("""
    <div class="hero">
        <h1>Leave History</h1>
        <p>Leave requests, leave types and approval status.</p>
    </div>
    """, unsafe_allow_html=True)

    approved = leaves["status"].astype(str).str.lower().eq("approved").sum()
    pending = leaves["status"].astype(str).str.lower().eq("pending").sum()
    rejected = leaves["status"].astype(str).str.lower().eq("rejected").sum()

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        metric_card("TOTAL REQUESTS", f"{len(leaves):,}", "All records")
    with c2:
        metric_card("APPROVED", f"{approved:,}", "Approved requests")
    with c3:
        metric_card("PENDING", f"{pending:,}", "Awaiting decision")
    with c4:
        metric_card("REJECTED", f"{rejected:,}", "Rejected requests")

    col1, col2 = st.columns(2)

    with col1:
        type_data = leaves["type"].fillna("Unknown").value_counts()
        if not type_data.empty:
            fig = px.pie(
                values=type_data.values,
                names=type_data.index,
                hole=.5,
                title="Leave Types"
            )
            st.plotly_chart(chart_layout(fig), use_container_width=True)

    with col2:
        status_data = leaves["status"].fillna("Unknown").value_counts()
        if not status_data.empty:
            fig = px.bar(
                x=status_data.index,
                y=status_data.values,
                labels={"x": "Status", "y": "Requests"},
                title="Leave Status"
            )
            st.plotly_chart(chart_layout(fig), use_container_width=True)

    view = format_dates(leaves, ["start", "end"])
    cols = [
        c for c in [
            "username", "name", "department", "type",
            "start", "end", "reason", "status"
        ] if c in view.columns
    ]
    show_table(view[cols], 500)
    csv_download(view[cols], "leave_history.csv")


# =========================================================
# PAYROLL ANALYTICS
# =========================================================

elif selected_page == "Payroll Analytics":

    st.markdown("""
    <div class="hero">
        <h1>Payroll Analytics</h1>
        <p>Gross salary, deductions, net salary and payment status.</p>
    </div>
    """, unsafe_allow_html=True)

    gross = payroll["gross_salary"].sum()
    deductions = payroll["deduction"].sum()
    net = payroll["net_salary"].sum()

    paid_amount = payroll.loc[payroll["paid"], "net_salary"].sum()
    unpaid_amount = payroll.loc[~payroll["paid"], "net_salary"].sum()

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        metric_card("GROSS PAYROLL", money(gross), "Before deductions")
    with c2:
        metric_card("DEDUCTIONS", money(deductions), "Recorded deductions")
    with c3:
        metric_card("NET PAYROLL", money(net), "After deductions")
    with c4:
        metric_card("UNPAID AMOUNT", money(unpaid_amount), "Unpaid records")

    col1, col2 = st.columns(2)

    with col1:
        summary = pd.DataFrame({
            "Category": ["Gross Salary", "Deductions", "Net Salary"],
            "Amount": [gross, deductions, net]
        })

        fig = px.bar(
            summary,
            x="Category",
            y="Amount",
            color="Category",
            text="Amount",
            title="Payroll Totals"
        )
        fig.update_traces(texttemplate="%{y:,.0f}", textposition="outside")
        st.plotly_chart(chart_layout(fig), use_container_width=True)

    with col2:
        summary = pd.DataFrame({
            "Status": ["Paid", "Unpaid"],
            "Amount": [paid_amount, unpaid_amount]
        })

        fig = px.pie(
            summary,
            names="Status",
            values="Amount",
            hole=.55,
            title="Payment Status"
        )
        st.plotly_chart(chart_layout(fig), use_container_width=True)

    if not payroll.empty:
        dept_data = (
            payroll.assign(
                department=payroll["department"].fillna("Unknown")
            )
            .groupby("department", as_index=False)["net_salary"].sum()
        )

        fig = px.bar(
            dept_data,
            x="department",
            y="net_salary",
            color="department",
            title="Net Payroll by Department"
        )
        st.plotly_chart(chart_layout(fig), use_container_width=True)

    view = payroll.copy()
    view["Payment Status"] = view["paid"].map({
        True: "Paid", False: "Unpaid"
    })

    cols = [
        c for c in [
            "username", "name", "department", "month",
            "gross_salary", "deduction", "net_salary", "Payment Status"
        ] if c in view.columns
    ]

    show_table(view[cols], 500)
    csv_download(view[cols], "payroll_analytics.csv")


# =========================================================
# DATA EXPORT - NO RULES TAB
# =========================================================

elif selected_page == "Data Export":

    st.markdown("""
    <div class="hero">
        <h1>Data Export</h1>
        <p>Download company HR records as CSV files.</p>
    </div>
    """, unsafe_allow_html=True)

    export_data = {
        "Employee Database": users,
        "Attendance Record": attendance,
        "Leave History": leaves,
        "Payroll Analytics": payroll
    }

    dataset_name = st.selectbox(
        "Select dataset",
        list(export_data.keys())
    )

    selected_data = export_data[dataset_name].copy()
    selected_data = selected_data.drop(
        columns=["password", "password_hash"],
        errors="ignore"
    )

    if "paid" in selected_data.columns:
        selected_data["paid"] = selected_data["paid"].map({
            True: "Paid",
            False: "Unpaid"
        })

    selected_data = format_dates(
        selected_data, ["date", "start", "end"]
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        metric_card("DATASET", dataset_name, "Current selection")
    with c2:
        metric_card("TOTAL ROWS", f"{len(selected_data):,}", "Available records")
    with c3:
        metric_card("TOTAL COLUMNS", f"{len(selected_data.columns):,}", "Fields")

    tab_export, tab_preview = st.tabs([
        "Export Data",
        "Preview Data"
    ])

    with tab_export:
        csv_download(
            selected_data,
            dataset_name.lower().replace(" ", "_") + ".csv",
            "Download Selected CSV"
        )

        st.markdown("#### Download All Datasets")

        filenames = {
            "Employee Database": "employee_database.csv",
            "Attendance Record": "attendance_records.csv",
            "Leave History": "leave_history.csv",
            "Payroll Analytics": "payroll_analytics.csv"
        }

        for name, frame in export_data.items():
            safe_frame = frame.drop(
                columns=["password", "password_hash"],
                errors="ignore"
            ).copy()

            if "paid" in safe_frame.columns:
                safe_frame["paid"] = safe_frame["paid"].map({
                    True: "Paid",
                    False: "Unpaid"
                })

            safe_frame = format_dates(
                safe_frame, ["date", "start", "end"]
            )

            st.download_button(
                f"Download {name}",
                data=safe_frame.to_csv(index=False).encode("utf-8-sig"),
                file_name=filenames[name],
                mime="text/csv",
                key=f"export_{name}"
            )

    with tab_preview:
        show_table(selected_data, 450)


# =========================================================
# FIND EMPLOYEE
# =========================================================

elif selected_page == "Find Employee":

    st.markdown("""
    <div class="hero">
        <h1>Find Employee</h1>
        <p>Search employee profiles and view their related HR records.</p>
    </div>
    """, unsafe_allow_html=True)

    search_query = st.text_input(
        "Search by name, employee ID, email, department or designation",
        placeholder="Enter employee details..."
    )

    if search_query.strip():

        mask = pd.Series(False, index=users.index)

        for column in [
            "username", "name", "email", "department", "designation"
        ]:
            if column in users.columns:
                mask |= users[column].fillna("").astype(str).str.contains(
                    search_query.strip(),
                    case=False,
                    regex=False
                )

        matched = users[mask]

        if matched.empty:
            st.warning("Koi employee match nahi hua.")
        else:
            st.success(f"{len(matched)} employee record(s) found.")

            for _, emp in matched.iterrows():
                emp_id = str(emp.get("username", ""))

                with st.expander(
                    f"{emp.get('name', 'Employee')} — {emp_id}",
                    expanded=len(matched) == 1
                ):
                    c1, c2 = st.columns(2)

                    with c1:
                        st.markdown("#### Employee Profile")
                        st.write(f"**Employee ID:** {emp_id}")
                        st.write(f"**Name:** {emp.get('name', 'N/A')}")
                        st.write(f"**Email:** {emp.get('email', 'N/A')}")
                        st.write(f"**Department:** {emp.get('department', 'N/A')}")
                        st.write(f"**Designation:** {emp.get('designation', 'N/A')}")

                    with c2:
                        st.markdown("#### Salary Profile")
                        st.write(f"**Monthly Salary:** {money(emp.get('salary', 0))}")

                        emp_payroll = payroll[
                            payroll["username"].astype(str) == emp_id
                        ]

                        if not emp_payroll.empty:
                            latest = emp_payroll.iloc[-1]
                            st.write(f"**Payroll Month:** {latest.get('month', 'N/A')}")
                            st.write(f"**Gross Salary:** {money(latest.get('gross_salary', 0))}")
                            st.write(f"**Deductions:** {money(latest.get('deduction', 0))}")
                            st.write(f"**Net Salary:** {money(latest.get('net_salary', 0))}")
                            st.write(
                                f"**Payment Status:** "
                                f"{'Paid' if latest.get('paid', False) else 'Unpaid'}"
                            )
                        else:
                            st.info("Payroll record nahi mila.")

                    st.markdown("#### Attendance History")

                    emp_attendance = attendance[
                        attendance["username"].astype(str) == emp_id
                    ].copy()

                    emp_attendance = format_dates(
                        emp_attendance, ["date"]
                    )

                    att_cols = [
                        c for c in [
                            "date", "check_in", "check_out", "status", "hours"
                        ] if c in emp_attendance.columns
                    ]

                    show_table(emp_attendance[att_cols], 220)

                    st.markdown("#### Leave History")

                    emp_leaves = leaves[
                        leaves["username"].astype(str) == emp_id
                    ].copy()

                    emp_leaves = format_dates(emp_leaves, ["start", "end"])

                    leave_cols = [
                        c for c in [
                            "type", "start", "end", "reason", "status"
                        ] if c in emp_leaves.columns
                    ]

                    show_table(emp_leaves[leave_cols], 220)

    else:
        st.info("Employee ko search karne ke liye search box mein details likhein.")


# =========================================================
# FOOTER
# =========================================================

st.markdown("---")
st.markdown("""
<div style="text-align:center;color:#94a3b8;font-size:12px;padding:8px;">
    Company HR Analytics · Workforce Intelligence Platform
</div>
""", unsafe_allow_html=True)

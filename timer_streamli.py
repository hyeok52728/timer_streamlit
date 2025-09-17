"""
모의수사경진대회 시각 타이머 (Streamlit + Supabase 공용 타이머 최종 버전)
- 모든 사용자가 동일한 값을 보도록 Supabase DB에 공용 상태 저장/로드
- 실행:  streamlit run timer_streamlit.py
- 배포:  Streamlit Community Cloud에 올리고, Settings → Secrets에 SUPABASE_URL / SUPABASE_KEY 설정
- 시간대: Asia/Seoul 고정

requirements.txt 예시
---------------------
streamlit
supabase
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from supabase import create_client, Client

# ========================= 설정 ========================= #
REAL_BASE_HMS = {"h": 20, "m": 0, "s": 0}   # 현실 기준 시작 (기본: 20:00)
VIRT_BASE_HMS = {"h": 9,  "m": 0, "s": 0}   # 가상 기준 시작 (기본: 09:00)
DEFAULT_SPEED = 3                                # 기본 배율 ×3
SEOUL = ZoneInfo("Asia/Seoul")
TABLE_NAME = "timer_state"                       # Supabase 테이블 이름
ROW_ID = 1                                        # 단일 행 사용 (공용 타이머)

# ========================= 페이지 설정 & 스타일 ========================= #
st.set_page_config(page_title="모의수사경진대회 시각 타이머", layout="wide")
STYLE = """
<style>
  :root{ --bg:#000; --fg:#fff; --chip:#8f8f8f; --panel:#121212; --btn:#7f7f7f; --btn2:#2b2b2b; }
  .titlechip{ background:var(--chip); color:#111; font-weight:800; letter-spacing:.06em; padding:8px 12px; border-radius:10px; text-align:center; width:100%; }
  .panel{ background:var(--panel); border-radius:18px; padding:18px 22px; box-shadow:0 10px 30px rgba(0,0,0,.35); }
  .datebig{ font-size: clamp(28px, 6vw, 72px); font-weight:800; letter-spacing:.02em; margin:6px 0 10px; color:#dfe6ff; text-align:center; }
  .timebig{ font-size: clamp(80px, 17vw, 200px); font-weight:900; line-height:1; letter-spacing:.02em; text-align:center; word-break:keep-all; }
  .datesm{ font-size: clamp(16px, 3vw, 24px); color:#dfe6ff; margin:8px 0 6px; text-align:center; }
  .timesm{ font-size: clamp(40px, 8vw, 90px); font-weight:800; line-height:1.1; text-align:center; }
  .note{ margin-top:10px; color:#c5c5c5; font-size:12px; text-align:center; }
  .legend{ font-size:12px; color:#aaa; margin-top:6px }
  .block-container{padding-top: 0.8rem; padding-left: 1rem; padding-right: 2rem; max-width: 1200px;}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)

# ========================= DB 연결 ========================= #
@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client | None = None
try:
    supabase = get_client()
except Exception:
    st.warning("Supabase 연결 실패: secrets 설정을 확인하세요. (공용 동기화 없이 개인 세션으로 동작)")

# ========================= 유틸 ========================= #

def pad(n: int) -> str:
    return str(n).zfill(2)

def fmt_date(dt: datetime) -> str:
    return f"{dt.year}-{pad(dt.month)}-{pad(dt.day)}"

def fmt_hms(dt: datetime) -> str:
    return f"{pad(dt.hour)}:{pad(dt.minute)}:{pad(dt.second)}"

def fmt_adj(td: timedelta) -> str:
    total = int(td.total_seconds())
    sign = "+" if total >= 0 else "-"
    a = abs(total)
    d, rem = divmod(a, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return f"{sign}{d}일 {pad(h)}:{pad(m)}:{pad(s)}"

def get_default_real_base(now: datetime) -> datetime:
    base = now.replace(hour=REAL_BASE_HMS["h"], minute=REAL_BASE_HMS["m"], second=REAL_BASE_HMS["s"], microsecond=0)
    if now < base:
        base = base - timedelta(days=1)
    return base

def get_default_virt_base(real_base: datetime) -> datetime:
    return real_base.replace(hour=VIRT_BASE_HMS["h"], minute=VIRT_BASE_HMS["m"], second=VIRT_BASE_HMS["s"], microsecond=0)

def compute_virtual(now: datetime) -> datetime:
    """가상 = 가상 기준 + (현실경과 × 배율) + 보정 (정수초)"""
    rb = st.session_state.real_base
    vb = st.session_state.virt_base
    speed = st.session_state.speed
    adj = st.session_state.virt_adjust
    elapsed = now - rb
    vn = vb + timedelta(seconds=elapsed.total_seconds() * speed) + adj
    return vn.replace(microsecond=0)

# ========================= 원격 상태 I/O ========================= #

def to_iso(dt: datetime) -> str:
    return dt.astimezone(SEOUL).isoformat()

def from_iso(s: str) -> datetime:
    # fromisoformat이 tz-naive여도 astimezone 처리에서 오류 방지
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SEOUL)
    return dt.astimezone(SEOUL)

def load_remote_state() -> dict | None:
    if not supabase:
        return None
    try:
        resp = supabase.table(TABLE_NAME).select("*").eq("id", ROW_ID).execute()
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception:
        return None

def save_remote_state():
    if not supabase:
        return
    payload = {
        "id": ROW_ID,
        "real_base_iso": to_iso(st.session_state.real_base),
        "virt_base_iso": to_iso(st.session_state.virt_base),
        "virt_adjust_sec": int(st.session_state.virt_adjust.total_seconds()),
        "speed": int(st.session_state.speed),
        "updated_at": datetime.now(SEOUL).isoformat(),
    }
    try:
        supabase.table(TABLE_NAME).upsert(payload).execute()
        st.session_state.last_saved_at = payload["updated_at"]
    except Exception as e:
        st.warning("원격 저장 실패: " + str(e))

# 원격 → 로컬 적용

def apply_remote_state(row: dict):
    try:
        if row.get("real_base_iso"):
            st.session_state.real_base = from_iso(row["real_base_iso"]) 
        if row.get("virt_base_iso"):
            st.session_state.virt_base = from_iso(row["virt_base_iso"]) 
        st.session_state.virt_adjust = timedelta(seconds=int(row.get("virt_adjust_sec", 0)))
        st.session_state.speed = int(row.get("speed", DEFAULT_SPEED))
        st.session_state.last_loaded_at = row.get("updated_at")
    except Exception:
        pass

# ========================= 초기화 ========================= #
now0 = datetime.now(SEOUL)
if "initialized" not in st.session_state:
    real_base = get_default_real_base(now0)
    virt_base = get_default_virt_base(real_base)
    st.session_state.real_base = real_base
    st.session_state.virt_base = virt_base
    st.session_state.real_base_init = real_base
    st.session_state.virt_base_init = virt_base
    st.session_state.virt_adjust = timedelta(0)
    st.session_state.speed = DEFAULT_SPEED
    st.session_state.initialized = True
    st.session_state.last_loaded_at = None
    st.session_state.last_saved_at = None

    # 최초 기동 시 원격 상태 적용 (없으면 생성)
    row = load_remote_state()
    if row is None and supabase:
        save_remote_state()  # 기본값을 원격에 생성
    elif row is not None:
        apply_remote_state(row)

# ========================= 자동 새로고침 & 원격 pull ========================= #
try:
    st.autorefresh(interval=500, key="_tick")  # 0.5초
except Exception:
    pass

if supabase:
    row = load_remote_state()
    if row and row.get("updated_at") != st.session_state.last_loaded_at:
        apply_remote_state(row)

# ========================= 레이아웃 ========================= #
left, right = st.columns([1.6, 0.9])

with left:
    st.markdown('<div class="titlechip">모의수사경진대회 시각</div>', unsafe_allow_html=True)
    with st.container(border=False):
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        now1 = datetime.now(SEOUL)
        vnow = compute_virtual(now1)
        st.markdown(f'<div class="datebig">{fmt_date(vnow)}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="timebig">{fmt_hms(vnow)}</div>', unsafe_allow_html=True)
        rb = st.session_state.real_base
        vb = st.session_state.virt_base
        speed = st.session_state.speed
        meta = f"기준(현실 {fmt_hms(rb)}) → (가상 {fmt_hms(vb)}) · 배율 ×{speed}"
        st.markdown(f'<div class="note">{meta}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="titlechip">실제 시각</div>', unsafe_allow_html=True)
    with st.container(border=False):
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        now2 = datetime.now(SEOUL)
        st.markdown(f'<div class="datesm">{fmt_date(now2)}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="timesm">{fmt_hms(now2)}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("\n")
    c1, c2 = st.columns([1,1])
    with c1:
        st.button("일시 조정 열기/닫기", key="open_adjust", help="아래 조정 패널로 스크롤")
    with c2:
        st.caption("전체화면은 브라우저 F11을 이용하세요.")

st.divider()

# ========================= 조정 패널: 현실 기준 ========================= #
sub1, sub2 = st.columns(2)

with sub1:
    st.subheader("현실 기준 시작 (기본: 오늘 20:00, 이전이면 어제 20:00)")
    r1, r2, r3, r4, r5 = st.columns(5)
    changed = False
    if r1.button("+1일", use_container_width=True):
        st.session_state.real_base += timedelta(days=1); changed=True
    if r2.button("-1일", use_container_width=True):
        st.session_state.real_base -= timedelta(days=1); changed=True
    if r3.button("+1시간", use_container_width=True):
        st.session_state.real_base += timedelta(hours=1); changed=True
    if r4.button("-1시간", use_container_width=True):
        st.session_state.real_base -= timedelta(hours=1); changed=True
    if r5.button("초기화", use_container_width=True):
        st.session_state.real_base = st.session_state.real_base_init; changed=True

    r6, r7 = st.columns(2)
    if r6.button("+1분", use_container_width=True):
        st.session_state.real_base += timedelta(minutes=1); changed=True
    if r7.button("-1분", use_container_width=True):
        st.session_state.real_base -= timedelta(minutes=1); changed=True

    st.markdown(f"<div class='legend'>기준: {fmt_date(st.session_state.real_base)} {fmt_hms(st.session_state.real_base)}</div>", unsafe_allow_html=True)
    if changed:
        save_remote_state()

# ========================= 조정 패널: 가상 기준 ========================= #
with sub2:
    st.subheader("가상 기준 시작 (기본: 같은 날 09:00)")
    v1, v2, v3, v4, v5 = st.columns(5)
    changed2 = False
    if v1.button("+1일", use_container_width=True):
        st.session_state.virt_base += timedelta(days=1); changed2=True
    if v2.button("-1일", use_container_width=True):
        st.session_state.virt_base -= timedelta(days=1); changed2=True
    if v3.button("+1시간", use_container_width=True):
        st.session_state.virt_base += timedelta(hours=1); changed2=True
    if v4.button("-1시간", use_container_width=True):
        st.session_state.virt_base -= timedelta(hours=1); changed2=True
    if v5.button("초기화", use_container_width=True):
        st.session_state.virt_base = st.session_state.virt_base_init; changed2=True

    v6, v7 = st.columns(2)
    if v6.button("+1분", use_container_width=True):
        st.session_state.virt_base += timedelta(minutes=1); changed2=True
    if v7.button("-1분", use_container_width=True):
        st.session_state.virt_base -= timedelta(minutes=1); changed2=True

    st.markdown(f"<div class='legend'>기준: {fmt_date(st.session_state.virt_base)} {fmt_hms(st.session_state.virt_base)}</div>", unsafe_allow_html=True)
    if changed2:
        save_remote_state()

# ========================= 보정(현재 가상 시각 기준) ========================= #
st.subheader("경진대회 시각(현재) 보정")
st.caption("현재 화면의 대회 시각을 기준으로 하루/시간/분 단위로 보정하거나, 아래 입력값으로 바로 맞춥니다.")

adj_cols = st.columns(7)
btns = [
    ("+1일", timedelta(days=1)),
    ("-1일", -timedelta(days=1)),
    ("+1시간", timedelta(hours=1)),
    ("-1시간", -timedelta(hours=1)),
    ("+10분", timedelta(minutes=10)),
    ("+1분", timedelta(minutes=1)),
    ("-1분", -timedelta(minutes=1)),
]
changed3 = False
for i, (label, delta) in enumerate(btns):
    if adj_cols[i].button(label, use_container_width=True):
        st.session_state.virt_adjust += delta
        changed3 = True

vnow_live = compute_virtual(datetime.now(SEOUL))
st.markdown(f"<div class='legend'>현재 대회 시각: {fmt_date(vnow_live)} {fmt_hms(vnow_live)}</div>", unsafe_allow_html=True)

c_date, c_time, c_apply, c_reset = st.columns([1.2, 1.2, 1.5, 1])
with c_date:
    date_input = st.date_input("날짜", value=vnow_live.date())
with c_time:
    time_input = st.time_input("시간", value=vnow_live.time().replace(microsecond=0))
with c_apply:
    if st.button("지금 시각을 이 값으로 맞춤", use_container_width=True):
        target = datetime.combine(date_input, time_input).replace(tzinfo=SEOUL)
        nowx = datetime.now(SEOUL)
        base_no_adj = st.session_state.virt_base + (nowx - st.session_state.real_base) * st.session_state.speed
        st.session_state.virt_adjust = target - base_no_adj
        changed3 = True
with c_reset:
    if st.button("보정 초기화", use_container_width=True):
        st.session_state.virt_adjust = timedelta(0)
        changed3 = True

st.markdown(f"<div class='legend'>보정: {fmt_adj(st.session_state.virt_adjust)}</div>", unsafe_allow_html=True)
if changed3:
    save_remote_state()

# ========================= 배율 ========================= #
st.subheader("배율 (현실 → 가상)")
sp_cols = st.columns(6)
changed4 = False
for i, sp in enumerate([1, 2, 3, 4, 6, 9]):
    if sp_cols[i].button(f"×{sp}", use_container_width=True):
        st.session_state.speed = sp
        changed4 = True
st.markdown(f"<div class='legend'>현재 배율: ×{st.session_state.speed}</div>", unsafe_allow_html=True)
if changed4:
    save_remote_state()

st.divider()

# ========================= 초기화 & 안내 ========================= #
c_l, c_r = st.columns([1, 1])
with c_l:
    if st.button("모두 초기화"):
        nowx = datetime.now(SEOUL)
        st.session_state.real_base = get_default_real_base(nowx)
        st.session_state.virt_base = get_default_virt_base(st.session_state.real_base)
        st.session_state.real_base_init = st.session_state.real_base
        st.session_state.virt_base_init = st.session_state.virt_base
        st.session_state.virt_adjust = timedelta(0)
        st.session_state.speed = DEFAULT_SPEED
        save_remote_state()
with c_r:
    st.caption("*전체화면은 브라우저(F11) 또는 OS 단축키를 이용하세요. 모든 조정은 DB에 저장되어 공용으로 반영됩니다.")

# ========================= 배포용 참고 (Supabase 테이블) ========================= #
with st.expander("Supabase 테이블 생성 SQL (참고)"):
    st.code(
        """
create table if not exists public.timer_state (
  id int primary key,
  real_base_iso text,
  virt_base_iso text,
  virt_adjust_sec int default 0,
  speed int default 3,
  updated_at timestamptz default now()
);
insert into public.timer_state (id) values (1)
on conflict (id) do nothing;
        """,
        language="sql",
    )

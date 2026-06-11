import streamlit as st
import cv2
import os
import json
import base64
import tempfile
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Image, Paragraph, Spacer, PageBreak, Table, TableStyle, Flowable,
    KeepTogether,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── ページ設定 ──────────────────────────────────────────
st.set_page_config(
    page_title="動画→PDF 操作手順書メーカー",
    page_icon="🍳",
    layout="wide",
)

# ── クックパッド風デザイン CSS ───────────────────────────
st.markdown("""
<style>
/* 全体: noto-sans + 詰め組み + 温かみのあるオフホワイト背景 */
html, body, [class*="st-"], .stApp {
    font-family: "Noto Sans JP", noto-sans, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, arial, sans-serif !important;
    letter-spacing: -0.4px;
    font-feature-settings: "liga";
    color: #0f0f0f;
}
.stApp { background-color: #f8f6f2; }

/* 見出し: weight 600 で統一（700は使わない） */
h1, h2, h3, h4 { font-weight: 600 !important; color: #0f0f0f; }
h1 { font-size: 26px !important; }
h2 { font-size: 18px !important; line-height: 28px; }
h3 { font-size: 16px !important; line-height: 24px; }

/* プライマリボタン: クックパッドオレンジ */
.stButton > button[kind="primary"], .stDownloadButton > button {
    background-color: #f28c06 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 8px 24px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {
    background-color: #d97a00 !important;
}

/* セカンダリボタン */
.stButton > button[kind="secondary"] {
    background: #fff !important;
    color: #0f0f0f !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 8px !important;
    padding: 8px 24px !important;
    font-weight: 600 !important;
}

/* 入力欄 */
.stTextInput input, .stTextArea textarea {
    background: #fff !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 8px !important;
    font-size: 16px !important;
    color: #0f0f0f !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #f28c06 !important;
    box-shadow: 0 0 0 1px #f28c06 !important;
}

/* カード風: expander とアップローダー */
[data-testid="stExpander"] {
    background: #fff;
    border: 1px solid #e0e0e0 !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
[data-testid="stFileUploaderDropzone"] {
    background: #fff !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 12px !important;
}

/* フレームカード（列内の画像+入力をカード化） */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px;
}
[data-testid="stImage"] img { border-radius: 8px; }

/* キャプション */
.stCaption, [data-testid="stCaptionContainer"] { color: #757575 !important; font-size: 12px !important; }

/* スライダー・ラジオのアクセント */
.stSlider [data-baseweb="slider"] [role="slider"] { background-color: #f28c06 !important; }

/* マテリアルアイコンのフォントを復元（文字化け防止） */
[data-testid="stIconMaterial"], .material-symbols-rounded, .material-symbols-outlined,
span[class*="material-symbols"] {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined" !important;
    letter-spacing: normal !important;
}
</style>
""", unsafe_allow_html=True)

# ── カラーテーマ（サンプルマニュアル準拠）─────────────────
C_ORANGE = colors.HexColor("#F0900A")
C_ORANGE_LIGHT = colors.HexColor("#FDF3E3")
C_ORANGE_PALE = colors.HexColor("#FEF9F0")
C_TEXT = colors.HexColor("#333333")
C_GRAY = colors.HexColor("#777777")
C_BLUE_LIGHT = colors.HexColor("#E8F4FB")
C_BLUE = colors.HexColor("#2E86C1")
C_BORDER = colors.HexColor("#EEEEEE")

# ── フォント登録 ────────────────────────────────────────
@st.cache_resource
def register_font():
    candidates = [
        ("C:/Windows/Fonts/meiryo.ttc", 0),     # Meiryo 通常
        ("C:/Windows/Fonts/meiryob.ttc", 0),    # Meiryo 太字
        ("C:/Windows/Fonts/msgothic.ttc", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
        (os.path.join(os.path.dirname(__file__), "fonts", "NotoSansCJKjp-Regular.otf"), None),
    ]
    regular = bold = None
    for path, idx in candidates:
        if not os.path.exists(path):
            continue
        try:
            kwargs = {"subfontIndex": idx} if idx is not None and path.endswith(".ttc") else {}
            if regular is None:
                pdfmetrics.registerFont(TTFont("JFont", path, **kwargs))
                regular = "JFont"
            if bold is None and ("Bold" in path or path.endswith("b.ttc")):
                pdfmetrics.registerFont(TTFont("JFontB", path, **kwargs))
                bold = "JFontB"
        except Exception:
            continue
    if regular is None:
        regular = "Helvetica"
    if bold is None:
        bold = regular
    return regular, bold

FONT, FONT_B = register_font()

# ── フレーム抽出 ────────────────────────────────────────
def extract_frames(video_path: str, interval_sec: float, out_dir: str, prefix: str):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        cap.release()
        return []
    interval_frames = max(1, int(fps * interval_sec))
    paths = []
    frame_num = 0
    idx = 0
    while frame_num < fc:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if ret:
            p = os.path.join(out_dir, f"{prefix}_{idx:03d}.jpg")
            cv2.imwrite(p, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            paths.append(p)
            idx += 1
        frame_num += interval_frames
    cap.release()
    return paths

# ── 角丸ボックス Flowable ───────────────────────────────
class RoundedBox(Flowable):
    """背景色つき角丸ボックスに内容(Flowableリスト)を載せる"""
    def __init__(self, content, width, bg=C_ORANGE_LIGHT, pad=5 * mm, radius=3 * mm, border=None):
        super().__init__()
        self.content = content
        self.box_width = width
        self.bg = bg
        self.pad = pad
        self.radius = radius
        self.border = border

    def wrap(self, availWidth, availHeight):
        inner_w = self.box_width - 2 * self.pad
        self.inner_heights = []
        total = 0
        for f in self.content:
            w, h = f.wrap(inner_w, availHeight)
            self.inner_heights.append(h)
            total += h
        self.height = total + 2 * self.pad
        return self.box_width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(self.bg)
        if self.border:
            c.setStrokeColor(self.border)
            c.roundRect(0, 0, self.box_width, self.height, self.radius, stroke=1, fill=1)
        else:
            c.roundRect(0, 0, self.box_width, self.height, self.radius, stroke=0, fill=1)
        y = self.height - self.pad
        inner_w = self.box_width - 2 * self.pad
        for f, h in zip(self.content, self.inner_heights):
            y -= h
            f.drawOn(c, self.pad, y)
        c.restoreState()

# ── PDF 生成 ────────────────────────────────────────────
def create_pdf(steps, output_path, title, subtitle="", phase_name=""):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=12 * mm, bottomMargin=14 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm,
    )
    W, _ = A4
    page_w = W - 28 * mm

    s_title = ParagraphStyle("t", fontName=FONT_B, fontSize=21, leading=30, textColor=colors.white)
    s_badge = ParagraphStyle("badge", fontName=FONT_B, fontSize=10, leading=14, textColor=colors.white)
    s_sub = ParagraphStyle("sub", fontName=FONT, fontSize=10.5, leading=16, textColor=colors.HexColor("#FFF3E0"))
    s_meta = ParagraphStyle("meta", fontName=FONT, fontSize=9.5, leading=13, textColor=colors.HexColor("#FFE0B2"))
    s_phase = ParagraphStyle("ph", fontName=FONT_B, fontSize=13, leading=18, textColor=colors.white)
    s_stepno = ParagraphStyle("no", fontName=FONT_B, fontSize=12, leading=16, textColor=colors.white, alignment=1)
    s_steptitle = ParagraphStyle("st", fontName=FONT_B, fontSize=13, leading=18, textColor=C_TEXT)
    s_body = ParagraphStyle("b", fontName=FONT, fontSize=10.5, leading=17, textColor=C_TEXT)
    s_tip_t = ParagraphStyle("tt", fontName=FONT_B, fontSize=10, leading=15, textColor=C_BLUE)
    s_tip = ParagraphStyle("tp", fontName=FONT, fontSize=9.5, leading=15, textColor=C_TEXT)
    s_point_t = ParagraphStyle("pt", fontName=FONT_B, fontSize=10, leading=15, textColor=C_ORANGE)

    story = []

    # ── 表紙ヘッダー ──
    header_content = [
        Paragraph("― 操作マニュアル ―", s_badge),
        Spacer(1, 5 * mm),
        Paragraph(title.replace("\n", "<br/>"), s_title),
    ]
    if subtitle:
        header_content += [Spacer(1, 4 * mm), Paragraph(subtitle, s_sub)]
    n_steps = len([s for s in steps if s["use"]])
    header_content += [
        Spacer(1, 5 * mm),
        Paragraph(f"全{n_steps}ステップ　／　作成日：{date.today().strftime('%Y/%m/%d')}", s_meta),
    ]
    story.append(RoundedBox(header_content, page_w, bg=C_ORANGE, pad=8 * mm, radius=5 * mm))
    story.append(Spacer(1, 8 * mm))

    # ── フェーズ見出し ──
    if phase_name:
        story.append(RoundedBox(
            [Paragraph(f"　{phase_name}", s_phase)],
            page_w, bg=C_ORANGE, pad=3.5 * mm, radius=3 * mm,
        ))
        story.append(Spacer(1, 6 * mm))

    # ── 各ステップ ──
    img_w = 62 * mm
    text_w = page_w - img_w - 10 * mm
    step_no = 0
    for s in steps:
        if not s["use"]:
            continue
        step_no += 1

        # ステップ見出し行（番号サークル＋タイトル）
        circle = Table([[Paragraph(str(step_no), s_stepno)]], colWidths=[9 * mm], rowHeights=[9 * mm])
        circle.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), C_ORANGE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ROUNDEDCORNERS", [12, 12, 12, 12]),
        ]))
        head = Table(
            [[circle, Paragraph(s["title"] or f"ステップ {step_no}", s_steptitle)]],
            colWidths=[12 * mm, page_w - 12 * mm],
        )
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, C_BORDER),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))

        # 画像
        img = cv2.imread(s["img"])
        h0, w0 = img.shape[:2]
        ih = img_w * h0 / w0
        pic = Image(s["img"], width=img_w, height=ih)

        # 説明テキスト群
        right = [Paragraph(s["desc"].replace("\n", "<br/>"), s_body)] if s["desc"] else []
        if s["tip"]:
            right.append(Spacer(1, 3 * mm))
            right.append(RoundedBox(
                [Paragraph("ポイント", s_tip_t), Spacer(1, 1.5 * mm),
                 Paragraph(s["tip"].replace("\n", "<br/>"), s_tip)],
                text_w, bg=C_BLUE_LIGHT, pad=3.5 * mm, radius=2 * mm,
            ))
        if not right:
            right = [Spacer(1, 1)]

        body = Table(
            [[pic, right]],
            colWidths=[img_w + 4 * mm, text_w + 6 * mm],
        )
        body.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))

        block = Table([[head], [body]], colWidths=[page_w])
        block.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(KeepTogether([block, Spacer(1, 8 * mm)]))

    doc.build(story)

# ── AI 自動生成（Claude API）────────────────────────────
AI_SCHEMA = {
    "type": "object",
    "properties": {
        "manual_title": {"type": "string", "description": "マニュアル全体のタイトル"},
        "manual_subtitle": {"type": "string", "description": "マニュアルの概要説明（1〜2文）"},
        "phase_name": {"type": "string", "description": "フェーズ見出し（例：PHASE 1 ○○する）"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "frame_index": {"type": "integer", "description": "使用するフレームの番号（0始まり）"},
                    "title": {"type": "string", "description": "ステップタイトル（〜する で終わる）"},
                    "description": {"type": "string", "description": "操作の説明文（2〜3文、です・ます調）"},
                    "tip": {"type": "string", "description": "補足ポイント。不要なら空文字"},
                },
                "required": ["frame_index", "title", "description", "tip"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["manual_title", "manual_subtitle", "phase_name", "steps"],
    "additionalProperties": False,
}


def ai_generate_steps(frame_paths, api_key, hint=""):
    """フレーム画像をClaudeに送り、キーシーン選別＋説明文生成"""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    content = []
    for i, fp in enumerate(frame_paths):
        # 長辺720pxに縮小してトークン節約
        img = cv2.imread(fp)
        h, w = img.shape[:2]
        scale = 720 / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        b64 = base64.standard_b64encode(buf.tobytes()).decode()
        content.append({"type": "text", "text": f"フレーム {i}:"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })

    hint_text = f"\n補足情報: {hint}" if hint else ""
    content.append({
        "type": "text",
        "text": (
            "これらは操作手順を撮影した動画から抽出したフレームです（時系列順・番号は0始まり）。"
            "操作マニュアルを作るために以下を行ってください:\n"
            "1. 手順として重要なキーフレームだけを選ぶ（ほぼ同じ画面の連続フレームは1枚に絞る）\n"
            "2. 各キーフレームにステップタイトル・説明文・補足ポイントを書く\n"
            "3. マニュアル全体のタイトル・概要・フェーズ見出しを提案する\n"
            "説明文は患者さんやスタッフが読んでも分かる、ていねいな日本語（です・ます調）で。"
            + hint_text
        ),
    })

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": AI_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        message = stream.get_final_message()
    text = next(b.text for b in message.content if b.type == "text")
    return json.loads(text)


# ════════════════════════════════════════════════════════
#  UI
# ════════════════════════════════════════════════════════
st.title("🎬 動画 → PDF 操作手順書メーカー")
st.caption("動画からフレームを抽出 → 使うシーンを選んで説明文を入力 → 本格マニュアルPDFを生成")

if "frames" not in st.session_state:
    st.session_state.frames = []       # list of file paths
    st.session_state.tmp_dir = None

# ── STEP 1: 動画アップロード＆フレーム抽出 ──
st.header("STEP 1️⃣ 動画をアップロード")
uploaded_files = st.file_uploader(
    "動画ファイル（複数可）", type=["mov", "mp4", "avi", "mkv"],
    accept_multiple_files=True,
)
interval_sec = st.slider("⏱ フレーム抽出間隔（秒）", 1, 10, 5)

if st.button("🎞 フレームを抽出する", disabled=not uploaded_files):
    if st.session_state.tmp_dir is None:
        st.session_state.tmp_dir = tempfile.mkdtemp()
    tmp = st.session_state.tmp_dir
    all_frames = []
    with st.spinner("フレーム抽出中..."):
        for i, uf in enumerate(uploaded_files):
            vp = os.path.join(tmp, uf.name)
            with open(vp, "wb") as f:
                f.write(uf.read())
            fdir = os.path.join(tmp, f"v{i:02d}")
            os.makedirs(fdir, exist_ok=True)
            all_frames += extract_frames(vp, interval_sec, fdir, f"v{i:02d}")
    st.session_state.frames = all_frames
    st.success(f"✅ {len(all_frames)} フレームを抽出しました。下で使うシーンを選んでください。")

# ── STEP 2: フレーム選択＆説明入力 ──
if st.session_state.frames:
    st.header("STEP 2️⃣ シーンを選んで説明を書く")
    st.caption("チェックを入れたフレームだけが PDF に載ります。タイトル・説明・ポイントを入力してください。")

    # ── AI 自動生成 ──
    with st.expander("🤖 AIで自動生成（キーシーン選別＋説明文作成）", expanded=True):
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "") if hasattr(st, "secrets") else ""
        if not api_key:
            api_key = st.text_input("Anthropic API キー", type="password",
                                    help="console.anthropic.com で取得できます")
        ai_hint = st.text_input("補足情報（任意）",
                                placeholder="例：歯科医院でiPhoneの写真をNEOに取り込む手順です")
        if st.button("✨ AIに自動生成してもらう", disabled=not api_key):
            with st.spinner("AIがフレームを解析中...（1〜2分かかります）"):
                try:
                    result = ai_generate_steps(st.session_state.frames, api_key, ai_hint)
                    # 全フレームをいったんオフに
                    for i in range(len(st.session_state.frames)):
                        st.session_state[f"use_{i}"] = False
                    # AIが選んだフレームに結果を流し込む
                    for step in result["steps"]:
                        i = step["frame_index"]
                        if 0 <= i < len(st.session_state.frames):
                            st.session_state[f"use_{i}"] = True
                            st.session_state[f"t_{i}"] = step["title"]
                            st.session_state[f"d_{i}"] = step["description"]
                            st.session_state[f"p_{i}"] = step["tip"]
                    st.session_state["ai_title"] = result["manual_title"]
                    st.session_state["ai_subtitle"] = result["manual_subtitle"]
                    st.session_state["ai_phase"] = result["phase_name"]
                    st.success(f"✅ AIが {len(result['steps'])} ステップを生成しました！下で確認・編集できます。")
                    st.rerun()
                except Exception as e:
                    st.error(f"AI生成エラー: {e}")

    steps = []
    cols_per_row = 3
    frames = st.session_state.frames
    for row_start in range(0, len(frames), cols_per_row):
        cols = st.columns(cols_per_row)
        for ci, fp in enumerate(frames[row_start:row_start + cols_per_row]):
            i = row_start + ci
            with cols[ci]:
                st.image(fp, use_container_width=True)
                use = st.checkbox(f"フレーム {i+1} を使う", key=f"use_{i}")
                title = desc = tip = ""
                if use:
                    title = st.text_input("ステップタイトル", key=f"t_{i}",
                                          placeholder="例：iPhoneをUSBケーブルでPCに接続する")
                    desc = st.text_area("説明文", key=f"d_{i}", height=100,
                                        placeholder="例：LightningケーブルまたはUSB-Cケーブルを使って…")
                    tip = st.text_input("💡 ポイント（任意）", key=f"p_{i}",
                                        placeholder="例：表示されない場合は「信頼」を先にタップ")
                steps.append({"img": fp, "use": use, "title": title, "desc": desc, "tip": tip})

    # ── STEP 3: マニュアル情報＆生成 ──
    st.header("STEP 3️⃣ マニュアル情報を入力して生成")
    st.session_state.setdefault("ai_title", "操作マニュアル")
    st.session_state.setdefault("ai_phase", "")
    st.session_state.setdefault("ai_subtitle", "")
    c1, c2 = st.columns(2)
    with c1:
        pdf_title = st.text_input("📕 マニュアルタイトル", key="ai_title")
        phase_name = st.text_input("🏷 フェーズ見出し（任意）", key="ai_phase",
                                   placeholder="例：PHASE 1　iPhoneをPCに接続する")
    with c2:
        pdf_subtitle = st.text_area("📄 サブタイトル・概要（任意）", key="ai_subtitle", height=100,
                                    placeholder="例：iPhoneで撮影した写真をNEOに取り込む手順をご説明します。")

    n_sel = len([s for s in steps if s["use"]])
    st.info(f"現在 **{n_sel} ステップ** が選択されています。")

    if st.button("▶ マニュアルPDFを生成する", type="primary", disabled=n_sel == 0):
        with st.spinner("PDF 生成中..."):
            out = os.path.join(st.session_state.tmp_dir, "manual.pdf")
            create_pdf(steps, out, pdf_title, pdf_subtitle, phase_name)
            with open(out, "rb") as f:
                pdf_bytes = f.read()
        st.success(f"✅ 生成完了！（{len(pdf_bytes)//1024} KB）")
        st.download_button("📥 PDF をダウンロード", data=pdf_bytes,
                           file_name=f"{pdf_title}.pdf", mime="application/pdf")

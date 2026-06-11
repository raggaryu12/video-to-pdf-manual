import streamlit as st
import cv2
import os
import glob
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Image, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── ページ設定 ──────────────────────────────────────────
st.set_page_config(
    page_title="動画→PDF 操作手順書メーカー",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 動画 → PDF 操作手順書メーカー")
st.caption("動画をアップロードするだけで、操作手順書 PDF を自動生成します。")

# ── フォント登録 ────────────────────────────────────────
@st.cache_resource
def register_font():
    font_name = "Helvetica"
    candidates = [
        # Windows
        "C:/Windows/Fonts/msgothic.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        # Linux (Streamlit Cloud)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf",
        # プロジェクト同梱
        os.path.join(os.path.dirname(__file__), "fonts", "NotoSansCJKjp-Regular.otf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                ext = os.path.splitext(path)[1].lower()
                kwargs = {"subfontIndex": 0} if ext == ".ttc" else {}
                pdfmetrics.registerFont(TTFont("JFont", path, **kwargs))
                font_name = "JFont"
                break
            except Exception:
                continue
    return font_name

FONT_NAME = register_font()

# ── フレーム抽出 ────────────────────────────────────────
def extract_frames(video_path: str, interval_sec: float, out_dir: str, prefix: str) -> int:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        cap.release()
        return 0
    interval_frames = max(1, int(fps * interval_sec))
    frame_num = 0
    idx = 0
    while frame_num < fc:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if ret:
            out_path = os.path.join(out_dir, f"{prefix}_{idx:03d}.jpg")
            cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            idx += 1
        frame_num += interval_frames
    cap.release()
    return idx

# ── PDF 生成 ────────────────────────────────────────────
def create_pdf(frame_dirs_prefixes: list, output_path: str, title: str, cols: int = 2):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )
    W, _ = A4
    page_w = W - 30 * mm

    title_style = ParagraphStyle(
        "Title", fontName=FONT_NAME, fontSize=20, spaceAfter=6,
        alignment=1, textColor=colors.HexColor("#2C3E50"),
    )
    h1_style = ParagraphStyle(
        "H1", fontName=FONT_NAME, fontSize=13, spaceAfter=4,
        spaceBefore=8, textColor=colors.HexColor("#1a5276"), leading=18,
    )
    step_style = ParagraphStyle(
        "Step", fontName=FONT_NAME, fontSize=9, spaceAfter=1,
        textColor=colors.HexColor("#2C3E50"), leading=13, alignment=1,
    )
    sub_style = ParagraphStyle(
        "Sub", fontName=FONT_NAME, fontSize=9,
        textColor=colors.HexColor("#7f8c8d"), leading=12, alignment=1,
    )

    story = []

    # 表紙
    story.append(Spacer(1, 25 * mm))
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("作成日: 2026年6月11日", sub_style))
    story.append(PageBreak())

    img_w = (page_w - (cols - 1) * 4 * mm) / cols
    img_h = img_w * 0.56  # 16:9 近似

    for section_idx, (frame_dir, prefix, section_name) in enumerate(frame_dirs_prefixes):
        frames = sorted(glob.glob(os.path.join(frame_dir, f"{prefix}_*.jpg")))
        if not frames:
            continue
        story.append(Paragraph(section_name, h1_style))
        story.append(Spacer(1, 2 * mm))

        for row_start in range(0, len(frames), cols):
            row_frames = frames[row_start: row_start + cols]
            img_cells = []
            cap_cells = []
            for i, fp in enumerate(row_frames):
                step_no = row_start + i + 1
                img_cells.append(Image(fp, width=img_w, height=img_h))
                cap_cells.append(Paragraph(f"Step {step_no}", step_style))
            # 列数に満たない場合は空白で埋める
            while len(img_cells) < cols:
                img_cells.append("")
                cap_cells.append("")

            col_w = img_w + 2 * mm
            t = Table(
                [img_cells, cap_cells],
                colWidths=[col_w] * cols,
            )
            t.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
            ]))
            story.append(t)
            story.append(Spacer(1, 2 * mm))

        story.append(PageBreak())

    doc.build(story)

# ── UI ─────────────────────────────────────────────────
uploaded_files = st.file_uploader(
    "📎 動画ファイルをアップロード（複数可）",
    type=["mov", "mp4", "avi", "mkv"],
    accept_multiple_files=True,
)

col1, col2 = st.columns(2)
with col1:
    interval_sec = st.slider("⏱ フレーム抽出間隔（秒）", min_value=1, max_value=10, value=3)
with col2:
    cols_choice = st.radio("🔲 1ページあたりの列数", options=[1, 2], index=1, horizontal=True)

pdf_title = st.text_input("📝 PDFタイトル", value="操作手順書")

if st.button("▶ PDF を生成する", type="primary", disabled=not uploaded_files):
    with tempfile.TemporaryDirectory() as tmp_dir:
        frame_dirs_prefixes = []
        progress = st.progress(0, text="動画を処理中...")

        for i, uploaded_file in enumerate(uploaded_files):
            # 動画を一時ファイルに保存
            video_path = os.path.join(tmp_dir, uploaded_file.name)
            with open(video_path, "wb") as f:
                f.write(uploaded_file.read())

            # フレーム抽出
            prefix = f"video{i+1:02d}"
            frame_dir = os.path.join(tmp_dir, prefix)
            os.makedirs(frame_dir, exist_ok=True)

            section_name = f"パート {i+1}：{os.path.splitext(uploaded_file.name)[0]}"
            n = extract_frames(video_path, interval_sec, frame_dir, prefix)
            frame_dirs_prefixes.append((frame_dir, prefix, section_name))

            progress.progress(
                (i + 1) / len(uploaded_files) * 0.8,
                text=f"{uploaded_file.name} → {n} フレーム抽出完了",
            )

        # PDF 生成
        progress.progress(0.9, text="PDF を生成中...")
        pdf_path = os.path.join(tmp_dir, "output.pdf")
        create_pdf(frame_dirs_prefixes, pdf_path, pdf_title, cols=cols_choice)
        progress.progress(1.0, text="✅ 完了！")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        st.success(f"✅ PDF 生成完了！（{len(pdf_bytes) // 1024} KB）")
        st.download_button(
            label="📥 PDF をダウンロード",
            data=pdf_bytes,
            file_name=f"{pdf_title}.pdf",
            mime="application/pdf",
        )

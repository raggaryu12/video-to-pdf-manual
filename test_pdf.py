# create_pdf の単体テスト（streamlit をスタブして実行）
import sys
import types
import glob
import os

st = types.ModuleType("streamlit")
st.set_page_config = lambda **k: None
st.cache_resource = lambda f: f
def _noop(*a, **k):
    return None
for name in ["title", "caption", "header", "info", "success", "image",
             "text_input", "text_area", "checkbox", "slider", "button",
             "file_uploader", "columns", "spinner", "download_button",
             "markdown", "expander", "error", "rerun", "radio"]:
    setattr(st, name, _noop)
st.secrets = {}
class _State(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
st.session_state = _State(frames=[], tmp_dir=None)
sys.modules["streamlit"] = st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app

frames = sorted(glob.glob(r"C:\Users\pilil\Downloads\manual_frames\1416_*.jpg"))[:4]
steps = [
    {"img": frames[0], "use": True,
     "title": "iPhoneをUSBケーブルでPCに接続する",
     "desc": "口腔内写真の撮影が終わったら、LightningケーブルまたはUSB-Cケーブルを使ってiPhoneをPCに接続します。\nPCのUSBポートに差し込み、iPhoneの画面が点灯することを確認してください。",
     "tip": "ケーブルはiPhone付属品または認定品を使用してください。"},
    {"img": frames[1], "use": True,
     "title": "iPhoneの「許可」をタップする",
     "desc": "PCに接続するとiPhoneの画面にダイアログが表示されます。「許可」をタップしてください。",
     "tip": "「信頼しますか？」と先に表示される場合は「信頼」→「許可」の順でタップ。"},
    {"img": frames[2], "use": True,
     "title": "エクスプローラーでDCIMフォルダを開く",
     "desc": "PCのエクスプローラーから Apple iPhone → Internal Storage → DCIM を開きます。",
     "tip": ""},
    {"img": frames[3], "use": False, "title": "", "desc": "", "tip": ""},
]

out = r"C:\Users\pilil\Downloads\test_manual_v2.pdf"
app.create_pdf(
    steps, out,
    title="iPhoneで撮影した写真を\nNEOに取り込む方法",
    subtitle="iPhoneで口腔内写真を撮影し、「写真取り込み用」フォルダを経由してNEOに取り込む手順をご説明します。",
    phase_name="PHASE 1　iPhoneをPCに接続する",
)
print(f"OK: {out} ({os.path.getsize(out)//1024} KB)")

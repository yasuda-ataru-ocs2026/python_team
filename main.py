import os
import re
import traceback
import io
from fastapi import FastAPI, UploadFile, File, HTTPException, Request  # 💡 Requestを追加
from fastapi.responses import JSONResponse, HTMLResponse
# ==========================================
# [段落1] 外部ファイルを読み込むための道具を追加
# ==========================================
# 💡 `StaticFiles`（CSS用）と `Jinja2Templates`（HTML用）という、
# 外部のフォルダからファイルを読み込んで画面に映し出すための専用の道具を取り込みます。
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import easyocr
from PIL import Image, ImageOps
from google import genai
from google.genai import types

# --- デスクトップの「.env」読み込み設定 ---
from dotenv import load_dotenv
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", ".env")
load_dotenv(desktop_path)

app = FastAPI()

# ==========================================
# [段落2] 外部フォルダの場所をFastAPIに教えてあげる設定
# ==========================================
# 💡 「staticフォルダの中身はCSSだよ」「templatesフォルダの中にHTMLがあるよ」と
# FastAPIにそれぞれの部屋の場所を教えて、いつでも使えるようにスタンバイさせます。
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

reader = None
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ==========================================
# [段落3] トップページにアクセスした時、自作HTMLファイルを読み込んで表示
# ==========================================
# 💡 これまではコード内に直接HTMLを書いていましたが、
# `templates.TemplateResponse` を使うことで、`templates/index.html` の中身を
# 自動で読み込んでブラウザに表示してくれるようになります！スッキリ！
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ==========================================
# [段落4] レシートアップロードAPI（中身は1文字も変えずにそのまま）
# ==========================================
@app.post("/upload-receipt")
async def upload_receipt(file: UploadFile = File(...)):
    global reader
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください。")

    temp_file_path = f"temp_{file.filename}"
    try:
        if not GEMINI_API_KEY:
            return JSONResponse(status_code=500, content={
                "status": "error",
                "message": f"デスクトップの `.env` からキーを読み込めませんでした。探した住所: {desktop_path}"
            })

        if reader is None:
            reader = easyocr.Reader(['ja'])

        # --- [0] 画像の前処理 ---
        image_data = await file.read()
        image = Image.open(io.BytesIO(image_data))
        image = ImageOps.exif_transpose(image)
        image = ImageOps.grayscale(image)
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        image.save(temp_file_path)
        
        # --- [1] OCR文字起こし ---
        try:
            ocr_result = reader.readtext(temp_file_path, detail=0)
        except Exception as ocr_err:
            return JSONResponse(status_code=500, content={"status": "error", "message": f"EasyOCR失敗: {str(ocr_err)}"})

        raw_text = "\n".join(ocr_result)
        if not raw_text.strip():
            return JSONResponse(status_code=400, content={"status": "error", "message": "文字が検出できませんでした。"})

        # --- [2] 無料AI（Gemini）による脳内補正 ---
        store = "不明な店舗"
        date = "2026-01-01"
        price = 0
        category = "その他"
        
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"""
            あなたは優秀な家計簿アプリのデータ補正エンジンです。
            以下は、レシートをOCRで読み取った結果ですが、激しく文字化けしています。
            前後の文脈や、電話番号、うっすら残っている商品名、日付などの情報から人間の知恵で推測し、
            正しい【店舗名】【購入日付(YYYY-MM-DD)】【合計金額(数値のみ)】【カテゴリ(食費、学習費、日用品、その他のいずれか)】を推測して、必ず以下のJSONフォーマットでのみ返答してください。
            思考プロセスなどは一切出力せず、JSONデータのみを返してください。

            【出力フォーマット】
            {{"store": "店舗名", "date": "YYYY-MM-DD", "price": 0, "category": "カテゴリ"}}

            【文字化けしたレシートテキスト】
            {raw_text}
            """
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            
            ai_text = response.text
            json_match = re.search(r"\{.*\}", ai_text, re.DOTALL)
            if json_match:
                import json
                ai_data = json.loads(json_match.group(0))
                store = ai_data.get("store", store)
                date = ai_data.get("date", date)
                price = ai_data.get("price", price)
                category = ai_data.get("category", category)
                
        except Exception as ai_err:
            print(f"【AI補正エラー】簡易抽出に切り替えます: {ai_err}")
            if "2025" in raw_text or "2026" in raw_text:
                date_match = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", raw_text)
                if date_match:
                    date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

        return {
            "status": "success",
            "ocr_raw_text": raw_text,
            "parsed_data": {
                "store": store,
                "date": date,
                "price": price,
                "category": category
            }
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
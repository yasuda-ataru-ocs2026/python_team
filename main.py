import os
import re
import traceback
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import easyocr
from PIL import Image, ImageOps
from google import genai
from google.genai import types

# ==========================================
# [段落1] デスクトップの「正しい住所」を計算する
# ==========================================
# 💡 パソコンのログインユーザー名（例: `taro` や `admin` など）は人によって違います。
# `os.path.expanduser("~")` を使うことで、プログラムが自動的に
# 「いま使っているユーザーのホームフォルダ（C:/Users/ユーザー名）」を割り出してくれます。
# そこに `/Desktop/.env` を合流させることで、デスクトップにあるファイルの正しい住所（パス）が完成します。
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", ".env")

# ==========================================
# [段落2] デスクトップの鍵を狙い撃ちして自動読み込み
# ==========================================
# 💡 道具（`load_dotenv`）を使い、先ほど[段落1]で計算したデスクトップの住所を直接指定します。
# これにより、プログラムと同じフォルダではなく、デスクトップにある `.env` から
# 鍵（APIキー）をピンポイントで吸い上げることができるようになります。
from dotenv import load_dotenv
load_dotenv(desktop_path)

app = FastAPI()

reader = None

# ==========================================
# [段落3] 吸い上げた安全なAPIキーを取り出す
# ==========================================
# 💡 デスクトップの `.env` から読み込まれたデータの中から、"GEMINI_API_KEY" を取り出します。
# これでコード上には生のキーが残らないため、GitHub対策もバッチリ維持されます。
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

@app.post("/upload-receipt")
async def upload_receipt(file: UploadFile = File(...)):
    global reader
    
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください。")

    temp_file_path = f"temp_{file.filename}"
    
    try:
        # ==========================================
        # [段落4] デスクトップの鍵が読めているかの安全チェック
        # ==========================================
        # 💡 万が一、デスクトップに置いたファイルの文字が間違っていたり、
        # ファイルがうまく見つからなかった場合は、ここで分かりやすいエラーを出して教えてくれます。
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

@app.get("/")
def read_root():
    return {"message": "Receipt API with Gemini is running"}
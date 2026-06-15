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

app = FastAPI()

reader = None

# ==========================================
# [解説1] 安全なAPIキーの読み込み（コードの心臓部）
# ==========================================
# 💡 OS（パソコン環境）または `.env` ファイルからAPIキーを自動で取り出します。
# コード上に生のキーが残らないため、GitHubにアップロードしても絶対に怒られなくなります！
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

@app.post("/upload-receipt")
async def upload_receipt(file: UploadFile = File(...)):
    global reader
    
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください。")

    temp_file_path = f"temp_{file.filename}"
    
    try:
        # ==========================================
        # [解説2] APIキーが正しく設定されているかの事前チェック
        # ==========================================
        # 💡 万が一、.envファイルの書き間違いなどでキーが読み込めなかった場合、
        # 処理が進んでエラーになる前に、分かりやすい日本語でエラーを画面に返して教えてくれます。
        if not GEMINI_API_KEY:
            return JSONResponse(status_code=500, content={
                "status": "error",
                "message": "GEMINI_API_KEY が設定されていません。.env ファイルを確認してください。"
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
        
        # ==========================================
        # [解説3] 取り出した安全なキーを使ってAIを起動
        # ==========================================
        # 💡 上の「解説1」でローカルから安全に抜き取った `GEMINI_API_KEY` を使って、
        # GoogleのAI（Gemini）と通信を開始します。中身の処理は前回の強力な補正のままです。
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
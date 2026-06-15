import os
import re
import traceback
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import easyocr
from PIL import Image, ImageOps
# 💡 無料AIを使うためのライブラリ
from google import genai
from google.genai import types

app = FastAPI() # FastAPIのインスタンスを作成

reader = None # 最初はOCRリーダーはNoneにしておいて、メモリ節約

# 💡 ここにGeminiの無料APIキーを入れます（後述）
# 本来は環境変数が良いですが、今回は確実性を重視してコードに直接書けるようにします
GEMINI_API_KEY = "AQ.Ab8RN6JlNQp_3MIOFMeT053nOKifYlk_4Up5wLcOndKYQQw9Rg" 

@app.post("/upload-receipt")
async def upload_receipt(file: UploadFile = File(...)):
    global reader
    
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください。")

    temp_file_path = f"temp_{file.filename}"
    
    try:
        if reader is None:
            reader = easyocr.Reader(['ja']) # 日本語対応のOCRリーダーを初期化（最初の1回だけ時間がかかる）  

        # --- [0] 画像の前処理 　画像をクッキリきれいにする処理---
        image_data = await file.read() # アップロードされた画像データを読み込む
        image = Image.open(io.BytesIO(image_data)) #
        image = ImageOps.exif_transpose(image) # 画像の向きを正しくする
        image = ImageOps.grayscale(image) # グレースケールに変換してコントラストを上げる
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

        # --- [2] 💡 無料AI（Gemini）による超能力・脳内補正 ---
        store = "不明な店舗"
        date = "2026-01-01"
        price = 0
        category = "その他"
        
        if GEMINI_API_KEY != "AQ.Ab8RN6JlNQp_3MIOFMeT053nOKifYlk_4Up5wLcOndKYQQw9Rg":
            try:
                # AIの準備
                client = genai.Client(api_key=GEMINI_API_KEY)
                
                # AIへの指示缶（プロンプト）
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
                
                # 無料モデルのGemini 2.5 Flashを呼び出し
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                
                # AIの返答からJSONを抽出
                ai_text = response.text
                # 反応の中に ```json ... ``` が含まれる場合を考慮してトリミング
                json_match = re.search(r"\{.*\}", ai_text, re.DOTALL)
                if json_match:
                    import json
                    ai_data = json.loads(json_match.group(0))
                    store = ai_data.get("store", store)
                    date = ai_data.get("date", date)
                    price = ai_data.get("price", price)
                    category = ai_data.get("category", category)
                    
            except Exception as ai_err: #AIが失敗する可能性もあるので、例外処理で保険をかけておく
                print(f"【AI補正エラー】今回はAIの機嫌が悪かったため、通常の簡易抽出に切り替えます: {ai_err}")
                # AIがダメだった時のための保険（前回の簡易抽出）
                if "2025" in raw_text or "2026" in raw_text:
                    date_match = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", raw_text)
                    if date_match:
                        date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"
                price_match = re.search(r"ギユ35|釣|合計.*(\d[\d,]*)", raw_text) # 暫定

        return {
            "status": "success",
            "ocr_raw_text": raw_text, # どんな呪文だったかも一応確認用に残す
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
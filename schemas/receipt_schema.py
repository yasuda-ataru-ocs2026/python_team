# ④ データの型定義（バリデーション用）
import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from paddleocr import PaddleOCR
from openai import OpenAI
import json

app = FastAPI()

# 1. PaddleOCRの初期化 (初回実行時に自動で日本語モデルがダウンロードされます)
ocr = PaddleOCR(lang="japan", use_angle_cls=True)

# 2. OpenAIクライアントの初期化 (環境変数からAPIキーを読み込みます)
# ⚠️ ターミナルで export OPENAI_API_KEY="あなたのキー" もしくは
# Windowsなら set OPENAI_API_KEY="あなたのキー" を実行しておいてください。
client = OpenAI()

@app.post("/upload-receipt")
async def upload_receipt(file: UploadFile = File(...)):
    # --- 前処理: アップロードされた画像を一時保存 ---
    temp_file_path = f"temp_{file.filename}"
    try:
        with open(temp_file_path, "wb") as f:
            f.write(await file.read())
        
        # --- [1] PaddleOCR による文字起こし ---
        # cls=True で、画像が横向きや逆さになっていても自動補正します
        ocr_result = ocr.ocr(temp_file_path, cls=True)
        
        # 検出されたテキストだけを1つの文章に結合する
        detected_texts = []
        if ocr_result and ocr_result[0]:
            for line in ocr_result[0]:
                text = line[1][0]  # line[1][0] に認識された文字列が入っています
                detected_texts.append(text)
        
        raw_text = "\n".join(detected_texts)
        
        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="レシートから文字を検出できませんでした。")

        # --- [2] OpenAI API によるJSON構造化 & カテゴリ判定 ---
        # gpt-4o-mini を使うことで、テキストだけなら1回あたり0.01円以下に抑えられます
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "あなたは優秀な家計簿アシスタントです。提供されたレシートの文字起こしデータから、"
                        "【店舗名(store)】【日付(date, YYYY-MM-DD形式)】【合計金額(price, 数値型)】【カテゴリ(category)】を抽出し、"
                        "指定されたJSONフォーマットのみで返答してください。余計な解説文は一切含めないでください。\n\n"
                        "カテゴリは、おにぎりや惣菜なら「食費」、本や参考書なら「学習費」のようにAIで適切に分類してください。"
                    )
                },
                {
                    "role": "user",
                    "content": f"以下のレシートテキストを解析してJSONにしてください：\n\n{raw_text}"
                }
            ],
            # JSON形式での返却を保証する設定
            response_format={"type": "json_object"}
        )

        # AIから返ってきた文字列をPythonの辞書（JSON）に変換
        result_json = json.loads(response.choices[0].message.content)
        
        return {
            "status": "success",
            "ocr_raw_text": raw_text, # デバッグ用に元の文字起こしも含めておく
            "parsed_data": result_json
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # 一時ファイルの削除
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
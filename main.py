import os
import re
import traceback  # エラーを詳しく見るために追加
from fastapi import FastAPI, UploadFile, File, HTTPException  #Web APIのためのFastAPIと例外処理
import easyocr  # OCRライブラリのインポート

app = FastAPI()

# EasyOCRの初期化
reader = easyocr.Reader(['ja', 'en']) #日本語と英語の両方をサポートするように設定

CATEGORY_MAP = {
    "食費": ["おにぎり", "お茶", "弁当", "パン", "サンドイッチ", "サラダ", "スイーツ"],
    "学習費": ["参考書", "ノート", "ペン", "教科書", "雑誌", "本"],
    "日用品": ["ティッシュ", "洗剤", "シャンプー", "マスク"]
}

def detect_category(texts):  #テキストのリストからカテゴリを判定し、分類
    for text in texts:
        for category, keywords in CATEGORY_MAP.items():
            for keyword in keywords:
                if keyword in text:
                    return category
    return "その他"

@app.post("/upload-receipt")  #このURLに画像がアップロードされたときにこの関数が呼び出される
async def upload_receipt(file: UploadFile = File(...)): #画像を一時保存（EasyOCRに読み込ませたいから）
    temp_file_path = f"temp_{file.filename}"            #同上
    try:
        # 画像の一時保存
        #temp_file_path というパスにファイルを開く。"wb"はバイナリ書き込みモードを意味する。
        # ファイルが存在しない場合は新規作成される。
        #try with構文は、ファイルを開いている間にエラーが発生しても、ファイルが確実に閉じられるようにするためのもの。
        with open(temp_file_path, "wb") as f:
            f.write(await file.read())
        
        # --- [1] OCR文字起こし ---
        try:
            ocr_result = reader.readtext(temp_file_path, detail=0)
        except Exception as ocr_err:
            return {"status": "error", "message": f"EasyOCRの読み込みで失敗しました: {str(ocr_err)}"}

        raw_text = "\n".join(ocr_result)
        
        if not raw_text.strip():
            return {"status": "error", "message": "画像から文字が1文字も検出されませんでした。写真がボケていないか確認してください。"}

        # --- [2] データの抽出 (エラーが出ないように徹底ガード) ---
        store = "不明な店舗"
        date = "2026-01-01"
        price = 0
        
        # 読み込んだ画像のテキストから、店舗名、日付、金額を抽出するロジック。
        # 多分ここが自分たちで1番手を加えられる部分です。
        try:
            # 店舗名判定
            if "ローソン" in raw_text or "LAWSON" in raw_text:
                store = "ローソン"
            elif "セブン" in raw_text or "7-eleven" in raw_text:
                store = "セブンイレブン"
            elif "ファミリーマート" in raw_text or "FamilyMart" in raw_text:
                store = "ファミリーマート"
            elif len(ocr_result) > 0:
                store = ocr_result[0]

            # 日付抽出
            date_match = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", raw_text)
            if date_match:
                date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

            # 金額抽出
            for i, text in enumerate(ocr_result):
                if "合計" in text or "小計" in text or "点" in text:
                    numbers = re.findall(r"\d[\d,]*", "".join(ocr_result[i:i+2]))
                    if numbers:
                        price = int(numbers[-1].replace(",", ""))
                        break
            
            if price == 0:
                all_numbers = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", raw_text) if len(n) >= 2]
                if all_numbers:
                    price = max(all_numbers)
        except Exception as parse_err:
            # 万が一データ抽出でバグっても、ここでキャッチして500エラーを防ぐ
            return {
                "status": "parse_error",
                "message": f"データ抽出中にエラーが起きました: {str(parse_err)}",
                "ocr_raw_text": raw_text
            }

        category = detect_category(ocr_result)

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
        # ターミナルに詳細なエラー理由（赤文字の正体）を強制表示する
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
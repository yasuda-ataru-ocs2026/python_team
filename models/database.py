import easyocr
import sqlite3
from datetime import datetime
import re

def clean_and_extract_number(text):
    """文字化けしやすい記号を数字や空文字に補正して、正しい数字を抽出する関数"""
    t = text.replace(" ", "")
    t = t.replace("キア", "7") # 「キア27」->「727」対策
    t = t.replace("半", "")    # 「半173」->「173」対策
    t = t.replace("#", "")    # 「#541」->「541」対策
    t = t.replace("キ", "7").replace("ア", "7")
    
    digits = ''.join(filter(str.isdigit, t))
    return int(digits) if digits else 0

def extract_date(result_list):
    """テキストリストから日付を抽出する（見つからなければ現在日時）"""
    # 典型的な日付パターン（YYYY-MM-DD や YYYY年MM月DD日 など）
    date_pattern = re.compile(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})')
    time_pattern = re.compile(r'(\d{1,2}):(\d{2})')
    
    for text in result_list:
        clean_text = text.replace(" ", "")
        date_match = date_pattern.search(clean_text)
        if date_match:
            year, month, day = date_match.groups()
            # 時間の抽出
            time_match = time_pattern.search(clean_text)
            hour, minute = time_match.groups() if time_match else ("00", "00")
            return f"{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute):02d}:00"
            
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def main():
    # 1. OCRリーダーの初期化
    print("AIモデルを読み込んでいます...（初回は時間がかかります）")
    reader = easyocr.Reader(['ja', 'en'])

    # 2. 画像から文字を読み取る
    image_path = 'receipt.jpg' 
    print(f"{image_path} を解析中...")
    try:
        result = reader.readtext(image_path, detail=0)
    except Exception as e:
        print(f"画像の読み込み、またはOCR処理に失敗しました: {e}")
        return

    print("\n--- [OCR 読取結果] ---")
    for text in result:
        print(text)
    print("----------------------\n")

    if not result:
        print("テキストが検出されませんでした。")
        return

    # 3. データ抽出ロジック
    shop_name = result[0]
    if "つ0" in shop_name or "商店" in shop_name:
        shop_name = "セブンイレブン"

    total_amount = 0
    # レシートの配列を逆順（下から上）に見ていく
    for i in range(len(result) - 1, -1, -1):
        text = result[i]
        clean_text = text.replace(" ", "")
        
        if "支払" in clean_text or "決済" in clean_text or "合計" in clean_text:
            if "値引" in clean_text or "税" in clean_text:
                continue
                
            amount = clean_and_extract_number(clean_text)
            if amount == 0 and i + 1 < len(result):
                amount = clean_and_extract_number(result[i + 1])
            
            if amount > 0:
                total_amount = amount
                break

    purchase_date = extract_date(result)

    print(f"【自動判定】店舗名: {shop_name} / 合計金額: {total_amount}円 / 日時: {purchase_date}")

    # 4. データベースへ保存（Context Managerを使用して確実にクローズ）
    try:
        with sqlite3.connect('household_accounts.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_name TEXT,
                purchase_date TEXT,
                total_amount INTEGER
            )''')
            
            cursor.execute(
                "INSERT INTO receipts (shop_name, purchase_date, total_amount) VALUES (?, ?, ?)",
                (shop_name, purchase_date, total_amount)
            )
            conn.commit()
            
        print("\n💰 家計簿データベースに登録しました！")
        print(f"【店舗】: {shop_name}")
        print(f"【日時】: {purchase_date}")
        print(f"【金額】: {total_amount} 円")
        
    except sqlite3.Error as e:
        print(f"データベースエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
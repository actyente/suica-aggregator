import streamlit as st
import pandas as pd
import io
from pypdf import PdfReader
import re
import datetime

# --- パスワード認証関数 ---
def check_password():
    def password_entered():
        if st.session_state.get("password", "") == "1234":
            st.session_state["password_correct"] = True
            if "password" in st.session_state:
                del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.error("😕 パスワードが違います")
        return False
    else:
        return True

# --- Suica履歴のパース・日別集計関数（深夜0時またぎの前日紐付け対応） ---
def parse_suica_pdf(pdf_file_obj):
    reader = PdfReader(pdf_file_obj)
    all_lines = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            all_lines.extend(text.split("\n"))
            
    all_trips_records = []
    daily_fare_sum = {}
    
    # 対象年は現在の年またはデフォルト2026年等
    year_int = datetime.datetime.now().year
    # 仮の月（PDFの記載から取得するかデフォルト設定）
    m_int = 3  # デフォルト3月（必要に応じて変更可能）

    for line in all_lines:
        line_str = line.strip()
        
        # パターン1: 通常の乗車・降車行
        match_trip = re.search(r'^(-?[\d,]+)(\d{2})\s*(?:.*?)(?:入|＊入)\s*(.*?)\s*出\s*(.*?)(\d{2})$', line_str)
        if match_trip:
            raw_price = match_trip.group(1)
            stn_in = match_trip.group(3).replace(' ', ' ').strip()
            stn_out = match_trip.group(4).replace(' ', ' ').strip()
            day = int(match_trip.group(5))
            
            # 深夜跨ぎ（0時〜3時台）の判定
            time_match = re.search(r'(\d{2}):?(\d{2})', line_str)
            is_midnight = False
            if time_match:
                hour = int(time_match.group(1))
                if 0 <= hour <= 3:
                    is_midnight = True

            target_date = datetime.date(year_int, m_int, day)
            if is_midnight:
                target_date = target_date - datetime.timedelta(days=1)

            date_str = target_date.strftime("%Y-%m-%d")

            price_num_str = raw_price.replace(",", "").replace("-", "").replace("+", "")
            numeric_fare = int(price_num_str) if price_num_str.isdigit() else 0
            if numeric_fare > 10000:
                numeric_fare = numeric_fare // 100
            
            # 利用金額（マイナス表記のものが運賃支払い）
            fare_amount = numeric_fare if "-" in raw_price else 0

            all_trips_records.append({
                "日付": date_str,
                "乗車駅": stn_in,
                "降車駅": stn_out,
                "利用金額": f"¥{numeric_fare:,}" if "-" in raw_price else f"+¥{numeric_fare:,}"
            })

            if date_str not in daily_fare_sum:
                daily_fare_sum[date_str] = 0
            if "-" in raw_price:
                daily_fare_sum[date_str] += numeric_fare
            continue

        # パターン2: 精算行
        match_seisan = re.search(r'^(-?[\d,]+)(\d{2})\s*精\s*(.*?)(\d{2})$', line_str)
        if match_seisan:
            raw_price = match_seisan.group(1)
            stn_name = match_seisan.group(3).replace(' ', ' ').strip()
            day = int(match_seisan.group(4))
            
            time_match = re.search(r'(\d{2}):?(\d{2})', line_str)
            is_midnight = False
            if time_match:
                hour = int(time_match.group(1))
                if 0 <= hour <= 3:
                    is_midnight = True

            target_date = datetime.date(year_int, m_int, day)
            if is_midnight:
                target_date = target_date - datetime.timedelta(days=1)

            date_str = target_date.strftime("%Y-%m-%d")

            price_num_str = raw_price.replace(",", "").replace("-", "").replace("+", "")
            numeric_fare = int(price_num_str) if price_num_str.isdigit() else 0
            if numeric_fare > 10000:
                numeric_fare = numeric_fare // 100
            
            fare_amount = numeric_fare if "-" in raw_price else 0

            all_trips_records.append({
                "日付": date_str,
                "乗車駅": f"{stn_name}(精算)",
                "降車駅": "-",
                "利用金額": f"¥{numeric_fare:,}" if "-" in raw_price else f"+¥{numeric_fare:,}"
            })

            if date_str not in daily_fare_sum:
                daily_fare_sum[date_str] = 0
            if "-" in raw_price:
                daily_fare_sum[date_str] += numeric_fare

    # 日別集計のリスト作成
    daily_summary_records = []
    total_sum = 0
    for d_str in sorted(daily_fare_sum.keys()):
        amt = daily_fare_sum[d_str]
        total_sum += amt
        daily_summary_records.append({
            "日付": d_str,
            "日別利用合計金額": f"¥{amt:,}"
        })

    # 合計行の追加
    daily_summary_records.append({
        "日付": "【 合計 】",
        "日別利用合計金額": f"¥{total_sum:,}"
    })

    return pd.DataFrame(daily_summary_records), pd.DataFrame(all_trips_records)

# --- メイン画面 ---
def main():
    st.title("Suica利用履歴集計システム🐧")
    st.subheader("PDF明細の読み込みと日別集計")

    if not check_password():
        return

    st.success("認証成功")

    suica_file = st.file_uploader("Suica利用履歴 (PDF) をアップロードしてください", type=["pdf"])

    if suica_file is not None:
        if st.button("📊 Suica履歴を集計する"):
            try:
                with st.spinner("Suica履歴を解析中..."):
                    df_daily, df_all_trips = parse_suica_pdf(suica_file)

                if df_daily.empty:
                    st.warning("有効な履歴データを検出できませんでした。ファイルをご確認ください。")
                    return

                st.markdown("---")
                st.write("### 📋 集計結果")

                # タブによる表示切り替え
                tab1, tab2 = st.tabs(["📅 1日毎の合計金額一覧", "🎫 すべての利用履歴"])

                with tab1:
                    st.dataframe(df_daily, use_container_width=True)

                with tab2:
                    st.dataframe(df_all_trips, use_container_width=True)

                # Excelダウンロード機能
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_daily.to_excel(writer, sheet_name="日別集計", index=False)
                    df_all_trips.to_excel(writer, sheet_name="全履歴", index=False)
                output.seek(0)

                today_str = datetime.datetime.now().strftime("%Y%m%d")
                download_filename = f"Suica集計結果_{today_str}.xlsx"

                st.markdown("---")
                st.download_button(
                    label="📥 集計結果Excelをダウンロード",
                    data=output,
                    file_name=download_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main()
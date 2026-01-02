import gradio as gr
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import datetime
import os

# --- CONFIGURATION ---
HEADERS = {
    "User-Agent": "EVE Master Scanner/12.0 (Auto) (admin@example.com)",
    "Accept": "application/json"
}

HUBS = {
    "Jita 4-4 (The Forge)":       {"region": 10000002, "station": 60003760},
    "G-0Q86 (Curse - Angel Hub)": {"region": 10000012, "station": 60011740},
    "Amarr VIII (Domain)":        {"region": 10000043, "station": 60008494},
}

# Создаем папку для отчетов, если нет
if not os.path.exists("reports"):
    os.makedirs("reports")

# Глобальный флаг остановки
SHOULD_STOP = False

# --- API ---
def get_orders(region_id, order_type="all", page=1):
    url = f"https://esi.evetech.net/latest/markets/{region_id}/orders/"
    params = {"datasource": "tranquility", "order_type": order_type, "page": page}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json(), int(response.headers.get('X-Pages', 1))
        return [], 0
    except:
        return [], 0

def resolve_names(type_ids):
    url = "https://esi.evetech.net/latest/universe/names/"
    names_map = {}
    unique_ids = list(set(type_ids))
    for i in range(0, len(unique_ids), 1000):
        chunk = unique_ids[i:i+1000]
        try:
            response = requests.post(url, json=chunk, headers=HEADERS)
            if response.status_code == 200:
                for item in response.json():
                    names_map[item['id']] = item['name']
        except: pass
    return names_map

def get_history_stats(region_id, type_id):
    url = f"https://esi.evetech.net/latest/markets/{region_id}/history/"
    params = {"datasource": "tranquility", "type_id": type_id}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if not data: return 0, 0
            recent = data[-30:] 
            avg_vol = sum([d['volume'] for d in recent]) / len(recent)
            avg_price = sum([d['average'] for d in recent]) / len(recent)
            return avg_vol, avg_price
    except:
        return 0, 0

# --- DATA FETCH ---
def fetch_market_df(region_id, station_id, order_type="all", max_pages=0):
    first, total_pages = get_orders(region_id, order_type, 1)
    orders = list(first)
    
    limit = total_pages if max_pages == 0 else min(max_pages, total_pages)
    
    if limit > 1:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(get_orders, region_id, order_type, p): p for p in range(2, limit + 1)}
            for future in as_completed(futures):
                if SHOULD_STOP: break
                o, _ = future.result()
                if o: orders.extend(o)
    
    df = pd.DataFrame(orders)
    if df.empty: return pd.DataFrame()
    return df[df['location_id'] == station_id]

# --- LOGIC ---
def run_velocity_mode(hub_name, min_price, max_price, min_vol, min_daily_profit, scan_depth, yield_func):
    setup = HUBS[hub_name]
    yield_func(pd.DataFrame(), f"📥 Скачиваем ордера {hub_name}...")
    
    df = fetch_market_df(setup['region'], setup['station'], "all", scan_depth)
    if df.empty: return pd.DataFrame()
    
    buy = df[df['is_buy_order'] == True].groupby('type_id')['price'].max()
    sell = df[df['is_buy_order'] == False].groupby('type_id')['price'].min()
    
    res = pd.concat([buy, sell], axis=1).dropna()
    res.columns = ['Buy', 'Sell']
    res['Spread'] = res['Sell'] - res['Buy']
    res['ROI'] = (res['Spread'] / res['Buy']) * 100
    
    candidates = res[
        (res['Buy'] >= min_price) & (res['Buy'] <= max_price) &
        (res['ROI'] >= 10) & (res['ROI'] <= 300)
    ]
    
    yield_func(pd.DataFrame(), f"🔎 Анализ {len(candidates)} лотов...")
    top_ops = candidates.sort_values(by='Spread', ascending=False).head(300)
    names = resolve_names(list(top_ops.index))
    
    final_data = []
    processed = 0
    for type_id, row in top_ops.iterrows():
        if SHOULD_STOP: break
        vol, hist_price = get_history_stats(setup['region'], type_id)
        if vol < min_vol: continue
        if hist_price > 0 and (row['Buy'] > hist_price * 3): continue
        profit_day = row['Spread'] * vol
        if profit_day < min_daily_profit: continue

        final_data.append({
            'Name': names.get(type_id, str(type_id)),
            'Type': '⚡ TRADE',
            'Buy Price': row['Buy'],
            'Sell Price': row['Sell'],
            'Profit': row['Spread'],
            'ROI': row['ROI'],
            'Vol/Day': vol,
            'Est. Daily': profit_day
        })
        processed += 1
        if processed % 10 == 0: yield_func(pd.DataFrame(), f"🔎 Проверено {processed}...")

    return pd.DataFrame(final_data)

def run_import_mode(target_hub_name, min_roi, min_vol, include_empty, scan_depth, yield_func):
    target_setup = HUBS[target_hub_name]
    jita_setup = HUBS["Jita 4-4 (The Forge)"]
    
    yield_func(pd.DataFrame(), "📥 Качаем цены Житы...")
    jita_depth = 50 if scan_depth == 0 else scan_depth 
    jita_df = fetch_market_df(jita_setup['region'], jita_setup['station'], "sell", jita_depth)
    jita_prices = jita_df.groupby('type_id')['price'].min()
    
    if SHOULD_STOP: return pd.DataFrame()

    yield_func(pd.DataFrame(), f"📥 Качаем цены {target_hub_name}...")
    target_df = fetch_market_df(target_setup['region'], target_setup['station'], "sell", 0)
    if not target_df.empty:
        target_prices = target_df.groupby('type_id')['price'].min()
    else:
        target_prices = pd.Series(dtype=float)
    
    yield_func(pd.DataFrame(), "🧮 Сравниваем...")
    df = pd.DataFrame({'Jita': jita_prices, 'Target': target_prices})
    df = df.dropna(subset=['Jita'])
    
    df['Status'] = 'Active'
    df.loc[df['Target'].isna(), 'Status'] = 'Empty'
    df.loc[df['Status'] == 'Empty', 'Target'] = df['Jita'] * 2.0
    
    df['Profit'] = df['Target'] - df['Jita']
    df['ROI'] = (df['Profit'] / df['Jita']) * 100
    
    if not include_empty: df = df[df['Status'] == 'Active']
    candidates = df[df['ROI'] >= min_roi]
    
    top_ops = candidates.sort_values(by='ROI', ascending=False).head(300)
    names = resolve_names(list(top_ops.index))
    
    final_data = []
    for type_id, row in top_ops.iterrows():
        if SHOULD_STOP: break
        vol, _ = get_history_stats(target_setup['region'], type_id)
        if vol < min_vol: continue
        icon = "🚛 IMPORT" if row['Status'] == 'Active' else "⚠️ EMPTY"
        final_data.append({
            'Name': names.get(type_id, str(type_id)),
            'Type': icon,
            'Buy Price': row['Jita'],
            'Sell Price': row['Target'],
            'Profit': row['Profit'],
            'ROI': row['ROI'],
            'Vol/Day': vol,
            'Est. Daily': row['Profit'] * vol
        })
    return pd.DataFrame(final_data)

# --- CONTROL ---
def stop_process():
    global SHOULD_STOP
    SHOULD_STOP = True
    return "🛑 ОСТАНОВКА..."

def master_loop(mode, hub, min_p, max_p, vol, profit, roi, empty, depth, loop_mode, interval):
    global SHOULD_STOP
    SHOULD_STOP = False
    
    cycle_count = 0
    
    while True:
        cycle_count += 1
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        
        # 1. ЗАПУСК СКАНЕРА
        if mode == "💰 Торговля (Jita)":
            res = run_velocity_mode(hub, min_p, max_p, vol, profit, depth, lambda d, m: None) # yield заглушка
            prefix = "TRADE"
        else:
            res = run_import_mode(hub, roi, vol, empty, depth, lambda d, m: None)
            prefix = "IMPORT"
            
        if SHOULD_STOP:
            yield pd.DataFrame(), "🛑 Скан прерван пользователем.", None
            break

        # 2. ОБРАБОТКА И СОХРАНЕНИЕ
        if not res.empty:
            res = res.sort_values(by='Est. Daily', ascending=False)
            
            # Форматирование для экрана
            display = res.copy()
            for c in ['Buy Price', 'Sell Price', 'Profit', 'Est. Daily']: 
                display[c] = display[c].map('{:,.0f}'.format)
            display['ROI'] = display['ROI'].map('{:.1f}%'.format)
            display['Vol/Day'] = display['Vol/Day'].map('{:.1f}'.format)
            
            # АВТО-СОХРАНЕНИЕ (В папку reports)
            filename = f"reports/{prefix}_{hub[:4]}_{timestamp}.csv"
            res.to_csv(filename, index=False)
            
            msg = f"✅ Цикл #{cycle_count} завершен. Сохранено: {filename}"
            yield display, msg, filename
        else:
            yield pd.DataFrame(), f"⚠️ Цикл #{cycle_count}: Ничего не найдено.", None
            
        # 3. ЛОГИКА ЦИКЛА
        if not loop_mode:
            break
            
        # Таймер ожидания
        wait_seconds = interval * 60
        for i in range(wait_seconds):
            if SHOULD_STOP: break
            yield display if not res.empty else pd.DataFrame(), f"⏳ Ждем след. скан ({wait_seconds - i}с)...", None
            time.sleep(1)
            
        if SHOULD_STOP:
            yield pd.DataFrame(), "🛑 Остановлено.", None
            break

# --- UI ---
CSS = """
.gradio-container {background-color: #111827; color: #e5e7eb}
"""

with gr.Blocks(title="EVE Master v12.0 Auto", css=CSS) as demo:
    gr.Markdown("# 🛸 EVE Master Scanner v12.0 (Automation Edition)")
    
    with gr.Row():
        mode_radio = gr.Radio(["💰 Торговля (Jita)", "🚛 Импорт (Curse)"], value="🚛 Импорт (Curse)", label="Режим")
        hub_drop = gr.Dropdown(list(HUBS.keys()), value="G-0Q86 (Curse - Angel Hub)", label="Хаб")

    with gr.Group():
        gr.Markdown("### ⚙️ Настройки Сканирования")
        with gr.Row():
            vol_sl = gr.Slider(0.1, 1000, value=0.1, label="Min Vol/Day")
            depth_sl = gr.Slider(0, 100, value=0, label="Глубина (0=Всё)")
        with gr.Row(visible=False) as jita_opts:
            min_p = gr.Number(value=500000, label="Min Price")
            max_p = gr.Number(value=20000000, label="Max Price")
            min_daily = gr.Number(value=500000, label="Min Daily Profit")
        with gr.Row(visible=True) as imp_opts:
            roi_imp = gr.Slider(10, 500, value=30, label="Min ROI (%)")
            empty_chk = gr.Checkbox(value=True, label="Искать пустые рынки")

    with gr.Group():
        gr.Markdown("### 🔄 Автоматизация")
        with gr.Row():
            loop_chk = gr.Checkbox(label="🔁 Включить циклический скан", value=False)
            interval_sl = gr.Slider(1, 60, value=15, step=1, label="Интервал (минут)")

    with gr.Row():
        start_btn = gr.Button("🚀 START SCAN", variant="primary")
        stop_btn = gr.Button("🛑 STOP", variant="stop")

    dl = gr.File(label="Последний отчет")
    status = gr.Label(label="Статус")
    table = gr.Dataframe(label="Live Results")

    # UI Switch Logic
    def on_mode(m):
        if m == "💰 Торговля (Jita)":
            return gr.update(visible=True), gr.update(visible=False), "Jita 4-4 (The Forge)", 50, 10
        else:
            return gr.update(visible=False), gr.update(visible=True), "G-0Q86 (Curse - Angel Hub)", 0.1, 0

    mode_radio.change(on_mode, mode_radio, [jita_opts, imp_opts, hub_drop, vol_sl, depth_sl])

    start_btn.click(master_loop, 
                    [mode_radio, hub_drop, min_p, max_p, vol_sl, min_daily, roi_imp, empty_chk, depth_sl, loop_chk, interval_sl], 
                    [table, status, dl])
    
    stop_btn.click(stop_process, None, status)

if __name__ == "__main__":
    demo.queue().launch()
PATH = r"C:\Users\marut\Desktop\FnOBot\Dashboard\dashboard_core.py"
content = open(PATH, encoding='utf-8').read()

START = '    panels_html = ""\n    for sym in ["NIFTY", "BANKNIFTY"]:'
END   = '    return html'
si = content.find(START)
ei = content.find(END, si) + len(END)
if si == -1 or ei == -1:
    print("ERROR: markers not found"); exit(1)
print(f"Found section at chars {si}–{ei}")

NEW = '''    # ── Build per-symbol tab content ────────────────────────────────────────
    tab_contents = {}
    for sym in ["NIFTY", "BANKNIFTY"]:
        oi_data  = oi_data_map.get(sym, {})
        analysis = analysis_map.get(sym, {})
        delta    = delta_map.get(sym, {})
        signal, reasons = signals_map.get(sym, ("NEUTRAL", []))
        vwap     = vwap_map.get(sym, {})
        td       = tech_map.get(sym, {})
        iv       = iv_map.get(sym, {})
        conc     = conc_map.get(sym, {})
        setup    = setup_map.get(sym, {})
        fut      = futures_map.get(sym, {})
        next_oi  = (next_expiry_oi or {}).get(sym, {})
        next_ana = (next_analysis or {}).get(sym, {})

        spot     = oi_data.get("spot", 0)
        pcr      = analysis.get("pcr", 0)
        max_pain = analysis.get("max_pain", 0)
        expiry   = oi_data.get("expiry", "---")
        next_exp = next_oi.get("expiry", "---") if next_oi else "---"

        sig_col, sig_bg, sig_border = _sig_style(signal)
        best_setup  = setup.get("best_label", "---")
        best_score  = setup.get("best_score", 0)
        mood        = delta.get("mood", "---")
        reasons_str = "  .  ".join(reasons[:3]) if reasons else ""

        curr_table = _build_chain_table(
            sym, oi_data.get("chain", {}), {**analysis, "spot": spot},
            delta, expiry, oi_1hr_map.get(sym), oi_prevday_map.get(sym),
        )
        if next_oi and next_oi.get("chain"):
            nxt_table = _build_chain_table(sym, next_oi["chain"], {**next_ana, "spot": spot}, {}, next_exp)
            nxt_note  = '<div style="font-size:10px;color:#64748b;padding:4px 0">Refreshed every 15 min</div>'
        else:
            nxt_table = '<div style="color:#64748b;padding:20px;font-size:12px">Next expiry loading...</div>'
            nxt_note  = ""

        vwap_block = build_vwap_html(vwap, sym)
        tech_block = build_technicals_html(td, sym)
        iv_block   = build_iv_html(iv, sym)
        conc_block = build_oi_concentration_html(conc, sym)

        tab_contents[sym] = (
            f'<div class="sym-header">'
            f'<span class="sym-name">{sym}</span>'
            f'<span class="spot-price">{spot:,.1f}</span>'
            f'<span class="pcr-badge">PCR {pcr:.3f}</span>'
            f'<span class="mp-badge">MaxPain {max_pain:,.0f}</span>'
            f'<span class="expiry-badge">{expiry}</span>'
            f'<span class="signal-badge" style="background:{sig_border};color:{sig_col}">{signal}</span>'
            f'</div>'
            f'<div class="signal-card" style="background:{sig_bg};border-color:{sig_border}">'
            f'<div class="signal-main" style="color:{sig_col}">{signal}</div>'
            f'<div class="signal-reasons">{reasons_str}</div>'
            f'</div>'
            f'<div class="setup-card">{best_setup} ({best_score}/10) &nbsp;.&nbsp; {mood}</div>'
            f'<div class="ind-row">{vwap_block}{tech_block}{iv_block}{conc_block}</div>'
            f'<div class="chain-section">'
            f'<div class="tab-bar">'
            f'<button class="tab active" onclick="showChainTab(\'{sym}\',\'curr\',this)">Current: {expiry}</button>'
            f'<button class="tab" onclick="showChainTab(\'{sym}\',\'next\',this)">Next: {next_exp}</button>'
            f'</div>'
            f'<div id="chain-{sym}-curr" class="chain-tab-content">{curr_table}</div>'
            f'<div id="chain-{sym}-next" class="chain-tab-content" style="display:none">{nxt_note}{nxt_table}</div>'
            f'</div>'
        )

    movers_html = _build_movers_html(nifty50_stocks)
    spike_html  = _build_spike_html(delta_map)
    stocks_tab  = (
        '<div class="section-label" style="margin-top:0">Top Movers - Nifty 50</div>'
        + movers_html
        + '<div class="section-label" style="margin-top:16px">OI Spike Alerts</div>'
        + spike_html
    )

    vix_html = ""
    if india_vix > 0:
        vix_col  = "#e74c3c" if india_vix > 20 else "#2ecc71" if india_vix < 14 else "#e67e22"
        vix_html = f'<span class="vix-badge" style="color:{vix_col};font-weight:700">VIX {india_vix:.2f}</span>'

    stop_js = f"var _stopH={stop_h},_stopM={stop_m};"
    refresh_js = (
        stop_js + "\n"
        "var _refreshMs=3*60*1000,_startTime=new Date().getTime();\n"
        "function _isAfterStop(){var n=new Date();return(n.getHours()>_stopH)||(n.getHours()===_stopH&&n.getMinutes()>=_stopM);}\n"
        "function updateCountdown(){\n"
        "  if(_isAfterStop()){document.getElementById('countdown-footer').textContent='Market closed';return;}\n"
        "  var e=new Date().getTime()-_startTime,r=Math.max(0,Math.ceil((_refreshMs-e)/1000));\n"
        "  if(r===0){location.reload();return;}\n"
        "  var m=Math.floor(r/60),s=r%60;\n"
        "  document.getElementById('countdown-footer').textContent='Next refresh in '+m+'m '+(s<10?'0':'')+s+'s';\n"
        "}\n"
        "if(!_isAfterStop()){setInterval(updateCountdown,1000);setTimeout(function(){if(!_isAfterStop())location.reload();},_refreshMs);}\n"
        "else{document.addEventListener('DOMContentLoaded',function(){var el=document.getElementById('countdown-footer');if(el)el.textContent='Market closed';});}\n"
    )
    main_tab_js = (
        "function showMainTab(tabId,btn){\n"
        "  document.querySelectorAll('.main-tab-content').forEach(function(el){el.style.display='none';});\n"
        "  document.querySelectorAll('.main-tab-btn').forEach(function(el){el.classList.remove('active');});\n"
        "  document.getElementById('maintab-'+tabId).style.display='block';\n"
        "  btn.classList.add('active');\n"
        "}\n"
        "function showChainTab(sym,which,btn){\n"
        "  ['curr','next'].forEach(function(k){\n"
        "    var el=document.getElementById('chain-'+sym+'-'+k);\n"
        "    if(el)el.style.display=(k===which)?'block':'none';\n"
        "  });\n"
        "  btn.closest('.tab-bar').querySelectorAll('.tab').forEach(function(b){b.classList.remove('active');});\n"
        "  btn.classList.add('active');\n"
        "}\n"
    )
    main_tab_css = (
        ".main-tabs{display:flex;gap:0;background:var(--s1);border-bottom:2px solid var(--bd);position:sticky;top:52px;z-index:90;padding:0 24px;}\n"
        ".main-tab-btn{background:transparent;border:none;border-bottom:3px solid transparent;color:var(--mt);padding:12px 32px;"
        "font-family:'Inter',sans-serif;font-size:13px;font-weight:700;letter-spacing:1px;cursor:pointer;text-transform:uppercase;"
        "transition:all .2s;margin-bottom:-2px;}\n"
        ".main-tab-btn:hover{color:var(--tx);}\n"
        ".main-tab-btn.active{color:var(--ac);border-bottom-color:var(--ac);}\n"
        ".main-tab-content{display:none;padding:20px 24px;max-width:1500px;margin:0 auto;}\n"
    )

    nifty_html     = tab_contents.get("NIFTY", "")
    banknifty_html = tab_contents.get("BANKNIFTY", "")
    pull_time      = ts_str[13:21]
    excel_ts       = last_excel_ts or "---"

    html = (
        "<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
        "<meta charset='UTF-8'>\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
        f"<title>Nifty F&O Dashboard - {ts_str}</title>\n"
        "<style>\n"
        + _get_base_css() + "\n"
        + get_vwap_css() + "\n"
        + get_technicals_css() + "\n"
        + get_iv_css() + "\n"
        + get_oi_concentration_css() + "\n"
        + main_tab_css + "\n"
        "</style>\n</head>\n<body>\n"
        "<div class='topbar'>\n"
        "  <span class='topbar-title'>Nifty F&amp;O Bot v5 - Germany Edition</span>\n"
        f"  {vix_html}\n"
        f"  <span class='topbar-ts'>{ts_str}</span>\n"
        f"  <span class='topbar-meta'>Pull: {pull_time} . Excel: {excel_ts} . Scans: {scan_count}</span>\n"
        "</div>\n\n"
        "<div class='main-tabs'>\n"
        "  <button class='main-tab-btn active' onclick=\"showMainTab('nifty',this)\">&#9889; NIFTY</button>\n"
        "  <button class='main-tab-btn' onclick=\"showMainTab('banknifty',this)\">&#127970; BANKNIFTY</button>\n"
        "  <button class='main-tab-btn' onclick=\"showMainTab('stocks',this)\">&#128202; STOCKS</button>\n"
        "</div>\n\n"
        "<div id='maintab-nifty' class='main-tab-content' style='display:block'>\n"
        f"{nifty_html}\n"
        "</div>\n"
        "<div id='maintab-banknifty' class='main-tab-content'>\n"
        f"{banknifty_html}\n"
        "</div>\n"
        "<div id='maintab-stocks' class='main-tab-content'>\n"
        f"{stocks_tab}\n"
        "</div>\n\n"
        "<div class='footer'>\n"
        "  Nifty F&amp;O Bot v5 &nbsp;.&nbsp; Germany Edition &nbsp;.&nbsp;\n"
        f"  {ts_str} &nbsp;.&nbsp; <span id='countdown-footer'></span>\n"
        "</div>\n"
        "<script>\n"
        + main_tab_js + "\n"
        + refresh_js + "\n"
        "</script>\n</body>\n</html>"
    )

    os.makedirs(DATA_FOLDER, exist_ok=True)
    with open(DASH_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    return html'''

new_content = content[:si] + NEW + "\n" + content[ei:]
open(PATH, 'w', encoding='utf-8').write(new_content)
print(f"Done! {len(new_content):,} chars written to {PATH}")

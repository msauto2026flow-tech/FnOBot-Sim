"""
indicators/oi_concentration.py — Phase 4: OI Walls, Pinning Score, Concentration.

NOTE: Copy the full implementation from original indicators.py lines 2386-3164.
"""

from utils.logger import log

# TODO: Copy full implementation from original indicators.py

def compute_oi_concentration(chain, spot, atm, expiry_date): return {"error": "Not yet migrated"}
def compute_all_oi_concentration(oi_data_map): return {}
def score_oi_concentration(conc_data): return {"long_ce":0,"long_pe":0,"short_straddle":0,"short_strangle":0,"notes":[]}
def get_oi_concentration_excel_headers(): return ["Timestamp","Symbol","ATM","Pin_Score","Pin_Label","Pin_Strike","Nearest_CE_Wall","Nearest_PE_Wall","Conc_CE","Conc_PE","Symmetry","Zone_PCR_Upper","Zone_PCR_Lower","DTE"]
def get_oi_concentration_excel_values(conc_data, symbol, timestamp): return [timestamp,symbol]+["—"]*12
def format_oi_concentration_telegram_line(conc_data, symbol): return "OI Concentration: unavailable"
def format_oi_concentration_premarket_line(conc_data, symbol): return f"  {symbol} OI Conc: awaiting migration"
def build_oi_concentration_html(conc_data, symbol): return ""
def get_oi_concentration_css(): return ""

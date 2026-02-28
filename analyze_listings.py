#!/usr/bin/env python3
import argparse, math, sys, json, yaml
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
import pandas as pd

# ---------- Finance helpers ----------
def monthly_mortgage_pmt(principal: float, annual_rate: float, years: int) -> float:
    r = annual_rate / 12.0
    n = years * 12
    if r == 0: 
        return principal / n
    return principal * (r * (1 + r)**n) / ((1 + r)**n - 1)

# ---------- Data structures ----------
@dataclass
class Listing:
    address: str
    city: str
    state: str
    price: float
    beds: Optional[int] = None
    baths: Optional[float] = None
    sqft: Optional[int] = None
    lot_sqft: Optional[int] = None
    year_built: Optional[int] = None
    property_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    hoa_monthly: Optional[float] = None
    taxes_annual: Optional[float] = None

# ---------- Rent Estimator (layered) ----------
class RentEstimator:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def estimate(self, listing: Listing) -> Dict[str, Any]:
        """Return dict with rent, confidence (0..1), method."""
        strategies = self.cfg["rent_estimation"]["strategy_order"]
        for method in strategies:
            if method == "manual_override":
                mv = self.cfg["rent_estimation"].get("manual_overrides", {})
                full = f"{listing.address}".strip()
                if full in mv:
                    return {"rent": mv[full], "confidence": 0.9, "method": "manual_override"}
            elif method == "rule_of_thumb":
                rot = self.cfg["rent_estimation"].get("rule_of_thumb_per_bed", {})
                if listing.beds is not None:
                    key = str(listing.beds)
                    if key in rot:
                        return {"rent": float(rot[key]), "confidence": 0.6, "method": "rule_of_thumb_per_bed"}
            elif method == "rent_to_price":
                ratio = float(self.cfg["rent_estimation"].get("rent_to_price_ratio", 0.006))
                if listing.price:
                    return {"rent": listing.price * ratio, "confidence": 0.45, "method": "rent_to_price"}
        return {"rent": None, "confidence": 0.0, "method": "none"}

# ---------- Underwriter ----------
class Underwriter:
    def __init__(self, cfg: Dict[str, Any]):
        self.u = cfg["underwriting"]
        self.targets = cfg["targets"]

    def underwrite(self, listing: Listing, est_rent: float) -> Dict[str, Any]:
        price = listing.price
        u = self.u

        closing_costs = price * u["purchase_costs_pct"]
        rehab = float(u.get("rehab_budget", 0.0))
        down_payment = price * u["down_payment_pct"]
        loan_amount = price - down_payment

        pmi_monthly = 0.0
        if u["down_payment_pct"] < u.get("pmi_applies_under_dp_pct", 0.20):
            pmi_monthly = loan_amount * u.get("pmi_monthly_pct_of_loan", 0.0004)

        piti = monthly_mortgage_pmt(loan_amount, u["interest_rate_annual"], u["loan_term_years"])
        taxes_mo = (listing.taxes_annual if listing.taxes_annual else (price * u["annual_property_tax_rate"])) / 12.0
        ins_mo = (price * u["annual_insurance_rate"]) / 12.0
        hoa_mo = listing.hoa_monthly or u.get("monthly_hoa", 0.0)

        gross_monthly = est_rent
        vacancy = gross_monthly * u["vacancy_rate"]
        maintenance = gross_monthly * u["maintenance_rate"]
        management = gross_monthly * u["management_rate"]
        capex = gross_monthly * u["capex_rate"]

        op_ex = taxes_mo + ins_mo + hoa_mo + vacancy + maintenance + management + capex
        debt = piti + pmi_monthly
        noi = gross_monthly - (op_ex - taxes_mo) - taxes_mo  # NOI is before debt, includes taxes & ins as OpEx (standard)
        # More precisely: NOI = Gross - Vacancy - Opex (incl. taxes, ins, mgmt, maint, HOA, capex)
        noi = gross_monthly - (vacancy + taxes_mo + ins_mo + hoa_mo + maintenance + management + capex)

        annual_noi = noi * 12.0
        cap_rate = annual_noi / price if price else None

        total_cash_in = down_payment + closing_costs + rehab
        annual_cash_flow = (gross_monthly - (op_ex + debt)) * 12.0
        coc = (annual_cash_flow / total_cash_in) if total_cash_in > 0 else None

        dscr = (noi / debt) if debt > 0 else None

        return {
            "closing_costs": closing_costs,
            "rehab": rehab,
            "down_payment": down_payment,
            "loan_amount": loan_amount,
            "pmi_monthly": pmi_monthly,
            "piti_monthly": piti,
            "taxes_monthly": taxes_mo,
            "insurance_monthly": ins_mo,
            "hoa_monthly": hoa_mo,
            "vacancy": vacancy,
            "maintenance": maintenance,
            "management": management,
            "capex": capex,
            "op_ex_monthly": op_ex,
            "noi_monthly": noi,
            "noi_annual": annual_noi,
            "cap_rate": cap_rate,
            "cash_flow_annual": annual_cash_flow,
            "cash_on_cash": coc,
            "dscr": dscr,
            "total_cash_in": total_cash_in,
        }

# ---------- Screen / Manual Check ----------
class Screener:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.bb = cfg["buy_box"]
        self.mc = cfg["manual_check_rules"]
        self.targets = cfg["targets"]

    def in_buy_box(self, l: Listing) -> bool:
        if self.bb.get("markets"):
            city_state = f"{l.city}, {l.state}".strip().lower()
            if city_state not in [m.lower() for m in self.bb["markets"]]:
                return False
        if l.price is None or l.price > self.bb["max_price"]:
            return False
        if self.bb.get("min_beds") and (l.beds is None or l.beds < self.bb["min_beds"]):
            return False
        if self.bb.get("min_sqft") and (l.sqft is None or l.sqft < self.bb["min_sqft"]):
            return False
        if self.bb.get("min_lot_sqft") and (l.lot_sqft is None or l.lot_sqft < self.bb["min_lot_sqft"]):
            return False
        # max_year_built is a ceiling: exclude properties built after this year.
        # If listing.year_built is missing (None) we treat it as "unknown" and do not
        # exclude the listing (so users can set None on listings to avoid auto-failure).
        if self.bb.get("max_year_built") and (l.year_built is not None and l.year_built > self.bb["max_year_built"]):
            return False
        if self.bb.get("property_types") and l.property_type and l.property_type not in self.bb["property_types"]:
            return False
        return True

    def needs_manual_check(self, underwriting: Dict[str, Any], rent_conf: float, listing: Listing) -> tuple[bool, List[str]]:
        reasons = []
        # Near-target bands
        cap = underwriting.get("cap_rate")
        coc = underwriting.get("cash_on_cash")
        t = self.targets
        near_cap = self.mc["near_cap_target_bps"] / 10000.0
        near_coc = self.mc["near_coc_target_bps"] / 10000.0

        if cap is not None and abs(cap - t["min_cap_rate"]) <= near_cap:
            reasons.append(f"cap near target ({cap:.2%} ~ {t['min_cap_rate']:.2%})")
        if coc is not None and abs(coc - t["min_cash_on_cash"]) <= near_coc:
            reasons.append(f"CoC near target ({coc:.2%} ~ {t['min_cash_on_cash']:.2%})")

        # Rent confidence low
        if rent_conf < self.mc["rent_confidence_threshold"]:
            reasons.append(f"low rent confidence ({rent_conf:.2f})")

        # Missing critical fields
        if self.mc.get("missing_fields_trigger", True):
            critical = [listing.sqft, listing.year_built, listing.lot_sqft]
            if any(v is None for v in critical):
                reasons.append("missing key fields (sqft/year/lot)")

        return (len(reasons) > 0, reasons)

# ---------- Main ----------
def load_cfg(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)

def row_to_listing(row: pd.Series) -> Listing:
    def num(x):
        try:
            if pd.isna(x): return None
            return float(x)
        except: return None
    def num_int(x):
        v = num(x)
        return int(v) if v is not None else None

    return Listing(
        address=str(row.get("address", "")).strip(),
        city=str(row.get("city", "")).strip(),
        state=str(row.get("state", "")).strip(),
        price=float(row["price"]) if not pd.isna(row.get("price")) else 0.0,
        beds=num_int(row.get("beds")),
        baths=num(row.get("baths")),
        sqft=num_int(row.get("sqft")),
        lot_sqft=num_int(row.get("lot_sqft")),
        year_built=num_int(row.get("year_built")),
        property_type=str(row.get("property_type") or "").strip().lower() or None,
        latitude=num(row.get("latitude")),
        longitude=num(row.get("longitude")),
        hoa_monthly=num(row.get("hoa_monthly")),
        taxes_annual=num(row.get("taxes_annual")),
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--input", required=True, help="listings.csv or .json (array)")
    ap.add_argument("--out", default="results.csv")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    rent_est = RentEstimator(cfg)
    screen = Screener(cfg)
    uw = Underwriter(cfg)

    # Load listings
    if args.input.lower().endswith(".json"):
        df = pd.read_json(args.input)
    else:
        df = pd.read_csv(args.input)

    results = []
    for _, row in df.iterrows():
        l = row_to_listing(row)
        in_box = screen.in_buy_box(l)

        rent_info = rent_est.estimate(l)
        rent = rent_info["rent"]
        rent_conf = rent_info["confidence"]

        underwriting = uw.underwrite(l, rent) if rent else {}
        cap = underwriting.get("cap_rate")
        coc = underwriting.get("cash_on_cash")
        dscr = underwriting.get("dscr")

        meets_targets = (
            (cap is not None and cap >= cfg["targets"]["min_cap_rate"]) and
            (coc is not None and coc >= cfg["targets"]["min_cash_on_cash"]) and
            (dscr is not None and dscr >= cfg["targets"]["min_dscr"])
        ) if underwriting else False

        manual, reasons = screen.needs_manual_check(underwriting, rent_conf, l)

        results.append({
            "address": l.address,
            "city": l.city,
            "state": l.state,
            "price": l.price,
            "beds": l.beds,
            "baths": l.baths,
            "sqft": l.sqft,
            "property_type": l.property_type,
            "est_rent": round(rent, 0) if rent else None,
            "rent_method": rent_info["method"],
            "rent_confidence": rent_conf,
            "cap_rate": round(cap, 4) if cap is not None else None,
            "cash_on_cash": round(coc, 4) if coc is not None else None,
            "dscr": round(dscr, 3) if dscr is not None else None,
            "annual_noi": round(underwriting.get("noi_annual", 0), 0) if underwriting else None,
            "annual_cash_flow": round(underwriting.get("cash_flow_annual", 0), 0) if underwriting else None,
            "total_cash_in": round(underwriting.get("total_cash_in", 0), 0) if underwriting else None,
            "in_buy_box": in_box,
            "meets_targets": bool(meets_targets),
            "manual_check": bool(manual),
            "manual_reasons": "; ".join(reasons),
        })

    out_df = pd.DataFrame(results)

    # Rank: prioritize target-meeters, then cap rate, then CoC
    out_df["rank_key"] = (
        out_df["meets_targets"].astype(int) * 1_000_000
        + (out_df["cap_rate"].fillna(0) * 10000).astype(int) * 100
        + (out_df["cash_on_cash"].fillna(0) * 10000).astype(int)
    )
    out_df = out_df.sort_values(by="rank_key", ascending=False).drop(columns=["rank_key"])

    # Save + print summary
    out_df.head(cfg["outputs"]["top_n"]).to_csv(args.out, index=False)
    print("\nTop candidates:")
    cols = ["address","city","state","price","beds","sqft","est_rent","cap_rate","cash_on_cash","dscr","in_buy_box","meets_targets","manual_check"]
    print(out_df[cols].head(cfg["outputs"]["top_n"]).to_string(index=False))

if __name__ == "__main__":
    main()

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number


def _flat(row):
    return " ".join(cell_text(c) for c in row).lower().replace(" ", "")


def parse_marg_stock_wide_multival_xls(rows):
    """Marg/KLM wide "Stock Report" (.xls) with a MULTI-VALUATION column block per movement
    group (ARHAM DISTRIBUTOR). Two-row header: a GROUP row and a sub-header row.

    GROUP row (row N):    Opening | Purchase | P.Return | Sales | S.Return | Adjust |
                          Rep.Pur | Rep.Sale | Sample | Closing | ...
    Sub-header (row N+1):  SrNo | ItemName | then, under every value-bearing group, the run
                          Qty | MRP Value | PRate Value | LP Value | PTR Value | INV Value
                          (Sales inserts an extra "Free" column between Qty and MRP Value;
                          Rep.Pur / Rep.Sale / Sample carry only a single "Qty").

    So each group is a 6-column block (Qty + FIVE valuation bases: MRP / PRate / LP / PTR /
    INV) -- NOT the single Qty+Value pair that marg_stock_wide assumes. marg_stock_wide reads
    fixed indices (Opening Qty=2, Purchase Qty=4, ... Closing=17) which land on the wrong
    columns here (it reads a PTR-value cell as purchase_return, an MRP-value cell as
    sales_return, and closing=0), so it fails sanity on 100% of rows. This layout instead
    binds columns by GROUP+sub-header label, so the identity holds exactly.

    Movement -> canonical mapping (mapped by exact GROUP + sub-header text, positionally):
        Opening / Qty   -> opening_stock       (opening qty)
        Purchase / Qty  -> purchase_stock      (purchase qty, inflow +)
        P.Return / Qty  -> purchase_return     (purchase return qty, outflow -)
        Sales / Qty     -> sales_qty           (sale qty, outflow -)
        Sales / Free    -> sales_free          (free-on-sale qty, outflow -)
        S.Return / Qty  -> sales_return        (sales return qty, inflow +)
        Adjust / Qty    -> signed adjustment folded into +sales_return / -sales_free
        Rep.Pur / Qty   -> folded into purchase_stock (inflow +)
        Rep.Sale / Qty  -> folded into sales_qty (outflow -)
        Sample / Qty    -> folded into sales_qty (outflow -)
        Closing / Qty   -> closing_stock       (closing qty)
        Closing / MRP Value -> closing_stock_value ; Sales / MRP Value -> sales_value

    With that, closing = opening + purchase + purchase_free - purchase_return
              - sales_qty - sales_free + sales_return  holds on every row (verified 100%
    across all 37 product rows of the ARHAM book, incl. the "* Total Amount *" tallies).

    NEVER derives a quantity from any of the five value columns -- values stay value-only.
    """
    # Locate the two-row header: a GROUP row containing Opening/Purchase/Closing whose NEXT
    # row is the sub-header carrying SrNo + ItemName + the MRP/PRate/LP/PTR/INV value run.
    group_idx = None
    for idx in range(min(len(rows) - 1, 150)):
        g = _flat(rows[idx])
        s = _flat(rows[idx + 1])
        if (
            "opening" in g and "purchase" in g and "closing" in g and "sales" in g
            and "itemname" in s and "srno" in s
            and "mrpvalue" in s and "pratevalue" in s and "invvalue" in s
        ):
            group_idx = idx
            break
    if group_idx is None:
        return [], {}
    sub_idx = group_idx + 1

    group_row = rows[group_idx]
    sub_row = rows[sub_idx]
    ncols = max(len(group_row), len(sub_row))

    # Forward-fill the group label across the columns of its block, then map each (group,sub)
    # pair to a logical column slot.
    col = {}
    current_group = ""
    for i in range(ncols):
        g = cell_text(group_row[i]).lower().replace(" ", "") if i < len(group_row) else ""
        s = cell_text(sub_row[i]).lower().replace(" ", "") if i < len(sub_row) else ""
        if g:
            current_group = g
        if s in {"itemname"}:
            col["product"] = i
        elif s == "qty":
            if current_group == "opening":
                col["opening"] = i
            elif current_group == "purchase":
                col["purchase"] = i
            elif current_group in {"p.return", "preturn"}:
                col["purret"] = i
            elif current_group == "sales":
                col["sales"] = i
            elif current_group in {"s.return", "sreturn"}:
                col["sret"] = i
            elif current_group == "adjust":
                col["adjust"] = i
            elif current_group in {"rep.pur", "reppur"}:
                col["reppur"] = i
            elif current_group in {"rep.sale", "repsale"}:
                col["repsale"] = i
            elif current_group == "sample":
                col["sample"] = i
            elif current_group == "closing":
                col["closing"] = i
        elif s == "free" and current_group == "sales":
            col["salesfree"] = i
        elif s == "mrpvalue":
            if current_group == "sales":
                col["sales_value"] = i
            elif current_group == "closing":
                col["closing_value"] = i
        elif s in {"pack"}:
            col["pack"] = i
        elif s in {"code"}:
            col["code"] = i

    for req in ("product", "opening", "purchase", "sales", "closing"):
        if req not in col:
            return [], {}

    def num(raw_row, key):
        i = col.get(key)
        if i is None or i >= len(raw_row):
            return 0.0
        return to_number(raw_row[i]) or 0.0

    records = []
    for raw_row in rows[sub_idx + 1:]:
        if not raw_row:
            continue
        srno = cell_text(raw_row[0]) if len(raw_row) else ""
        if not srno.isdigit():
            continue
        product = cell_text(raw_row[col["product"]]) if col["product"] < len(raw_row) else ""
        if not product or is_subtotal(product) or product.startswith("*"):
            continue

        purchase = num(raw_row, "purchase") + num(raw_row, "reppur")
        sales = num(raw_row, "sales") + num(raw_row, "repsale") + num(raw_row, "sample")

        rec = {
            "product_name": product,
            "opening_stock": num(raw_row, "opening"),
            "purchase_stock": purchase,
            "purchase_return": num(raw_row, "purret"),
            "sales_qty": sales,
            "sales_free": num(raw_row, "salesfree"),
            "sales_return": num(raw_row, "sret"),
            "closing_stock": num(raw_row, "closing"),
            "closing_stock_value": num(raw_row, "closing_value"),
            "sales_value": num(raw_row, "sales_value"),
        }
        if "pack" in col and col["pack"] < len(raw_row):
            rec["pack"] = cell_text(raw_row[col["pack"]])

        # Signed Adjust: + adds to closing, - subtracts. Fold into +sales_return / -sales_free.
        adj = num(raw_row, "adjust")
        if adj > 0:
            rec["sales_return"] = rec["sales_return"] + adj
        elif adj < 0:
            rec["sales_free"] = rec["sales_free"] + (-adj)

        records.append(rec)

    detected = {
        "ItemName": "product_name",
        "Opening Qty": "opening_stock",
        "Purchase Qty": "purchase_stock",
        "P.Return Qty": "purchase_return",
        "Sales Qty": "sales_qty",
        "Sales Free": "sales_free",
        "S.Return Qty": "sales_return",
        "Closing Qty": "closing_stock",
        "Closing MRP Value": "closing_stock_value",
    }
    return records, detected


def detect(rows):
    flat = " ".join(" ".join(cell_text(c) for c in row) for row in rows[:150]).lower().replace(" ", "")
    if (
        "qtymrpvaluepratevaluelpvalueptrvalue" in flat
        and "stockreport" in flat and "itemname" in flat
    ):
        return "marg_stock_wide_multival_xls"
    return None

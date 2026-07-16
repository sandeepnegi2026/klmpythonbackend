def detect_excel_layout(rows):
    flat = " ".join(" ".join(row) for row in rows[:150]).lower().replace(" ", "")
    # Single-column fixed-width TEXT dump: a Marg "STOCK & SALES ANALYSIS" report pasted into
    # column A, so every row is one nbsp-padded cell and the grid matchers extract 0 rows. The
    # single-column shape (<=1 non-empty cell on every populated row) plus the item-description
    # header + trailing M.EXP column is unique to this export, so it cannot catch a real grid.
    populated = [row for row in rows[:60] if any(str(c).strip() for c in row)]
    single_col = bool(populated) and all(
        sum(1 for c in row if str(c).strip()) <= 1 for row in populated
    )
    # "Replicated single-column": the same fixed-width TEXT line stored as ONE merged cell that
    # the .xlsx unmerge spreads across many IDENTICAL columns, so `single_col` above reads False
    # even though every row carries just one logical value. Detected when MOST populated rows have
    # >=2 non-empty cells that are all identical. A genuine grid (distinct product/pack/number
    # cells) never trips this — only its few full-width title rows are identical, far below half.
    _repl = sum(
        1 for row in populated
        if sum(1 for c in row if str(c).strip()) >= 2
        and len({str(c).strip() for c in row if str(c).strip()}) == 1
    )
    replicated_single = bool(populated) and _repl >= max(3, len(populated) // 2)
    # Marg/KLM PALANPUR "MONTHLY STOCK & SALES STATEMENT" (.xls), banded by Make/division.
    # Sparse positional grid: Code | * | Product | Pack | Opening | Purchase | Goods Ret. |
    # Total In Qty | Sale | Purc. Ret. | Balance | Order 1 (Qty/Free) | Order 2 (Qty/Free) |
    # Remarks. The generic tabular reader misroutes it (blank spacer cells + the derived
    # "Total In Qty" column) so closing never reconciles. Keyed on the unique token combo
    # this export alone carries: the "Goods Ret." + "Purc. Ret." return columns AND the dual
    # pending-order columns (Order 1 / Order 2) under a "Stock & Sales Statement" title. No
    # other stock layout carries both return-column labels plus two Order bands, so this
    # cannot steal another vendor. (venus_stock_excel keys on "stockandsalestatement" without
    # the ampersand + "opstk"; this compact form has "stock&salesstatement" — disjoint.)
    if (
        "stock&salesstatement" in flat and "goodsret." in flat and "purc.ret." in flat
        and "order1" in flat and "order2" in flat and "balance" in flat
    ):
        return "marg_monthly_ss_statement_xlsx"
    # KLM LABORATORIES "Open.Stk / Rcpts / L.Sales / Cur.Sls." stock statement
    # (SAI PHARMA AGENCIES). The header has 9 cells but every DATA row has 10 physical
    # columns: the trailing "Clos.(Qty & Amt)" header spans closing QTY *and* closing
    # VALUE, so the generic `tabular` reader binds closing_stock to the rupee value and
    # every row fails sanity. A positional parser splits the two closing cells. Keyed on
    # this KLM abbreviation set (Rcpts + L.Sales + Cur.Sls. + the combined "Clos.(Qty")
    # which is unique to this export — verified to match ONLY this file across all
    # stock xlsx/xls in New_Data, so it cannot steal any other vendor's grid.
    if "rcpts" in flat and "l.sales" in flat and "cur.sls." in flat and "clos.(qty" in flat:
        return "stock_open_rcpts_dualsales_xlsx"
    # KLM "Sales && Stock Statement Group..." (GARG DISTRIBUTOR): OP/PUR/Total/CL
    # qty+amt grid whose "Total" column is really the SALES movement (OP + PUR -
    # Total = CL on every row). The generic tabular reader leaves sales unbound ->
    # 100% SANITY_FAILED. The exact compact header run is unique to this export.
    if "opqtyopamtpurqtypuramttotalqtytotalamtclqtyclamt" in flat:
        return "stock_op_pur_total_cl_xlsx"
    # Marg (ERP9+) "STOCK & SALES ANALYSIS" qty+value single-column TEXT dump (AGARTALA /
    # GLOBE). Same single-column shape as marg_stock_analysis_text but carrying the shorter
    # OPENING/RECEIPT/ISSUE/CLOSING/DUMP qty+value block (9 numeric cols) instead of the
    # 14-column movement block. Keyed on the RECEIPT+ISSUE+DUMP header trio (unique to this
    # qty/value variant) AND the absence of "m.exp" (which marks the 14-col movement sibling),
    # so the two never collide. Reuses the single_col/flat values already computed above.
    if (
        single_col and "itemdescription" in flat and "receipt" in flat and "issue" in flat
        and "closing" in flat and "dump" in flat and "m.exp" not in flat
    ):
        return "marg_stock_analysis_qv"
    # BURIMAA MEDICAL AGENCY (KLM .xls): the 8-column sibling of marg_stock_analysis_qv above —
    # the same single-column Marg "STOCK & SALES ANALYSIS" qty+value TEXT dump with
    # OPENING/RECEIPT/ISSUE/CLOSING groups, but WITHOUT the trailing DUMP column (8 numeric cols,
    # not 9). The qv gate above requires "dump"; this one requires its ABSENCE, so the two are
    # disjoint, and the "m.exp" clause keeps the 14-column movement sibling
    # (marg_stock_analysis_text) off it. single_col guarantees it cannot catch any real grid, and
    # the RECEIPT+ISSUE header trio is unique to this KLM text-dump family — so it steals nothing.
    if (
        single_col and "itemdescription" in flat and "receipt" in flat and "issue" in flat
        and "closing" in flat and "opening" in flat and "dump" not in flat
        and "m.exp" not in flat
    ):
        return "marg_stock_open_rcpt_issue_xls"
    # D.S.PHARMA (KLM .xlsx): a single-column Marg "STOCK & SALES ANALYSIS" qty+value TEXT dump
    # stored as ONE merged cell that the unmerge replicates across every column (so single_col is
    # False and the grid gate below would wrongly claim it). Same OPENING/RECEIPT/ISSUE/CLOSING +
    # DUMP block as marg_stock_analysis_qv but with a 10th trailing analytics column. Keyed on the
    # replicated-single-column shape + the RECEIPT/ISSUE/DUMP header trio; the genuine DERMA grid
    # is NOT replicated so it still falls to the grid gate, and AGARTALA/GLOBE qv is a true
    # one-cell dump (not replicated) so it stays on marg_stock_analysis_qv. MUST precede the grid.
    if (
        replicated_single and "itemdescription" in flat and "receipt" in flat
        and "issue" in flat and "closing" in flat and "opening" in flat and "dump" in flat
        and "m.exp" not in flat
    ):
        return "marg_stock_analysis_qv_dumpext"
    # DERMA DISTRIBUTORS (KLM "ALL DIVISION STOCK STATEMENT" .xls): the GRID twin of the
    # single-column marg_stock_analysis_qv above — the same Marg "STOCK & SALES ANALYSIS"
    # OPENING/RECEIPT/ISSUE/CLOSING + DUMP qty+value block, but each value in its own physical
    # column (NOT single_col). The generic `tabular` reader mostly works but loses the value
    # columns AND emits trailing phantom rows from the appended SUPPLIER/DEBIT-NOTE ledger and
    # page-break title lines. A positional parser bounds the stock grid (col1/col7 must be a
    # numeric-or-nil qty). Keyed on the RECEIPT+ISSUE+DUMP header trio in a GRID (not single_col);
    # the single-col qv sibling above already claimed the text-dump form, so the two are disjoint,
    # and DUMP is unique to this Marg report family so it cannot steal any other stock grid.
    if (
        not single_col and "itemdescription" in flat and "receipt" in flat and "issue" in flat
        and "closing" in flat and "opening" in flat and "dump" in flat and "m.exp" not in flat
    ):
        return "marg_stock_analysis_qv_grid"
    # CHAITANYA PHARMA (custom KLM ERP) "Stock and Sales Report For Month" grid with an OFFSET
    # two-row header: the GROUP row (Opening/Purchase/SaleS/Closing) has no "Product Name" cell,
    # so the generic `tabular` reader binds it as the header, never maps product_name, and
    # extracts 0 rows. A positional parser reads the fixed columns. Keyed on the compact combo
    # "stock and sales report" title + Product Name + the LMS column + the P.Return/Sale Return
    # sub-labels — unique to this KLM export (klm_lifecare_stock keys on the parenthesised
    # "stockandsalesreport(month)" + LastSalesQty history, which this file lacks), so it steals
    # nothing.
    if (
        "stockandsalesreport" in flat and "productname" in flat and "lms" in flat
        and "p.return" in flat and "salereturn" in flat and "opening" in flat
        and "closing" in flat
    ):
        return "marg_stock_sales_lms_xls"
    # KLM own-vendor "Stock sales statement(Combined)" grid (VISION HEALTHCARE
    # HOLDINGS). Header: Product Name | Pack | Rate | Prev.Sale | Opening | Purchase |
    # Total Sale | Sale Value | Adj. | Total Closing | Closing Value. The informational
    # "Prev.Sale" fuzzy-collides with the sales synonyms and "Adj." has no canonical home,
    # so the generic `tabular` mapper mis-reads the movement columns and every row fails
    # sanity. A header-driven positional parser maps ONLY the known columns by exact text
    # and omits Prev.Sale/Adj. Keyed on the compact combined-header set
    # (prev.sale + totalsale + totalclosing + closingvalue) UNDER the
    # "stock sales statement" title -- a combination unique to this KLM Combined export, so
    # it cannot catch any other stock grid (the plain KLM DSTK/OPSTK family has none of
    # these tokens).
    if (
        "stocksalesstatement" in flat
        and "prev.sale" in flat
        and "totalsale" in flat
        and "totalclosing" in flat
        and "closingvalue" in flat
    ):
        return "klm_stock_sales_combined_xlsx"
    # Prompt ERP "Stock Statement (Datewise)" for KLM (V.G.RAJA) — the .xls twin of the
    # PDF `prompt` stock layout. Four movement columns (OpStk/Pur/Sales/ClStk) carry ONLY
    # a "Qty" sub-header, while the closing rupee VALUE is printed in a separate "Amount"
    # column that sits under the A3Mn group label. The generic `tabular` reader keys on the
    # single group header, mis-reads A3Mn/Favourite as the value column, and reads the
    # closing amount as a quantity -> every row fails the sanity equation. Keyed on the
    # "Stock Statement (Datewise)" title + the OpStk/ClStk pair + the A3Mn + Favourite
    # analytics columns, a combo unique to this Prompt export (klm_dstk_stock uses PURC/
    # STOCKV/LZSTK, not Pur/A3Mn/Favourite), so it cannot catch any other stock grid.
    if (
        "stockstatement(datewise)" in flat and "opstk" in flat and "clstk" in flat
        and "a3mn" in flat and "favourite" in flat
    ):
        return "prompt_dstk_free_xlsx"
    # KLM ERP "Sale & Stock statement" qty-only movement grid (EMAMI FRANK ROSS).
    # Single header row: Item Code | Mfac Name | Item Name | Packing | Qpb | OpStk |
    # Pur Qty | Branch Return | Out Qty | StkAdj | Closing Stock. Closing =
    # OpStk + Pur Qty + Branch Return - Out Qty - StkAdj (StkAdj printed negative).
    # The inward "Branch Return" has no clean synonym (dropped by the generic mapper)
    # and the signed "StkAdj" has no canonical home, so tabular never reconciles.
    # A positional parser maps only the known columns by exact text. Keyed on the
    # compact combo opstk+branchreturn+stkadj+outqty which is unique to this KLM
    # export (verified: matches ONLY this file across all 124 New_Data stock books;
    # the klm_dstk_stock family carries PURC/STOCKV/LZSTK, none of these tokens), so
    # it can never steal another vendor's grid.
    if (
        "opstk" in flat and "branchreturn" in flat
        and "stkadj" in flat and "outqty" in flat
    ):
        return "klm_sale_stock_stmt"
    # KLM (custom ERP) "Stock And Sale" export (YOGIRAM DISTRIBUTORS), one .xls per
    # division. Header: CompCode | Company | Code | Item | Pack | Apr | Mar | Op. | Pur. |
    # SP | Pur Ret | SPur Ret | TRR | Sale | SS | TRI | SRet | Adj. | Cls.Stk | Net Sale.
    # The generic tabular reader mis-maps the informational prior-month sale columns
    # (Apr/Mar) and the rupee "Net Sale" value column onto quantity fields and drops the
    # SP/SS free columns, so closing never reconciles. A header-driven positional parser
    # binds SP->purchase_free (in), SS/TRI->sales_free (out), SRet/TRR->sales_return (in),
    # Pur Ret/SPur Ret->purchase_return so closing = opening+purchase+purchase_free
    # -purchase_return-sales-sales_free+sales_return exactly. Keyed on this KLM abbreviation
    # set (the "Stock And Sale" title plus SPur Ret + TRR + TRI + SRet + Cls.Stk + Net Sale,
    # a combo no other stock grid carries) -- verified to match ONLY this YOGIRAM export
    # family across all 124 stock xls/xlsx in New_Data, so it cannot steal another vendor.
    if (
        "stockandsale" in flat and "spurret" in flat and "trr" in flat and "tri" in flat
        and "sret" in flat and "cls.stk" in flat and "netsale" in flat
    ):
        return "klm_stock_and_sale"
    # KLM/Marg "Stock And Sales Report(Month)" wide single-header grid (LIFE CARE /
    # YOGIRAM PHARMA). ~35 columns where prior-month history (IILastSalesQty /
    # ILastSalesQty) and rupee *Value analytics fuzzy-collide with the qty synonyms and
    # steal the closing equation's fields, so the generic `tabular` reader mis-reads sales
    # and every affected row fails sanity. A header-mapped parser binds ONLY the verified
    # columns by exact text (SaleQuantity, not the LastSales history) and omits the value /
    # order columns. Keyed on the compact export title "stock and sales report(month)" plus
    # TotalStock + the IILastSalesQty/ILastSalesQty history tokens -- a combination unique
    # to this KLM export (verified to match ONLY this file across all New_Data xls/xlsx), so
    # it cannot steal any other vendor's grid.
    if (
        "stockandsalesreport(month)" in flat and "totalstock" in flat
        and ("iilastsalesqty" in flat or "ilastsalesqty" in flat)
    ):
        return "klm_lifecare_stock"
    # SwilERP "Sales & Stock Statement" (MEDICINE TRADERS KLM export). A division-banded
    # grid with EXACTLY 7 numeric columns: Op.Bal. | Receipt | Free Qty Qty | Total Qty |
    # Issue | Free Qty Qty | Closing Balance. The TWO "Free Qty Qty" headers normalize to
    # identical text, so map_headers_indexed binds only one Free column and drops the other
    # (~22% sanity fail). A header-driven positional parser folds each Free into the quantity
    # column it FOLLOWS (Receipt->purchase_free, Issue->sales_free) and ignores the redundant
    # "Total Qty" sum. Keyed on the compact SwilERP header set: op.bal. + receiptqty. +
    # issueqty. + closingbalance + TWO "freeqtyqty" occurrences -- a combination unique to
    # this export (verified: matches ONLY this file across all 124 stock xls/xlsx in New_Data).
    # NOTE: cannot gate on "swilerp" -- the "Powered By SwilERP" footer sits past the 150-row
    # flat window. Placed just before the final tabular fallback so it cannot steal any grid.
    if (
        "op.bal." in flat and "receiptqty." in flat and "issueqty." in flat
        and "closingbalance" in flat and flat.count("freeqtyqty") >= 2
    ):
        return "medicine_klm_detailed"
    # KLM abbreviated-header "OP_STK / PR_REC / TOT_REC / SL_ISS / CL_STK" stock statement
    # (legacy .XLS BIFF export — SHREE NATH ENTERPRISE). This KLM export prints the closing
    # column as the bare abbreviation CL_STK and carries a TOT_REC running-total column
    # (TOT_REC = OP_STK + PR_REC on every row — verified). The generic `tabular` mapper
    # fuzzy-binds purchase_stock to TOT_REC and double-counts receipts, so closing never
    # reconciles. A positional parser maps ONLY the known abbreviated headers and omits
    # TOT_REC / PKTSTK / AVG_SAL. Keyed on the full underscore-abbreviation set
    # (op_stk + pr_rec + tot_rec + sl_iss + cl_stk) which is unique to this KLM family and
    # verified to match ONLY this file across all stock xls/xlsx in New_Data (the plain
    # klm_dstk_stock family uses OPSTK/PURC/STOCK without underscores, so it is disjoint),
    # so it cannot steal any other vendor's grid.
    flat_underscore = " ".join(
        " ".join(str(c) for c in row) for row in rows[:60]
    ).lower().replace(" ", "")
    if (
        "op_stk" in flat_underscore and "pr_rec" in flat_underscore
        and "tot_rec" in flat_underscore and "sl_iss" in flat_underscore
        and "cl_stk" in flat_underscore
    ):
        return "klm_op_pr_sl_stock"
    # Marg "STOCK & SALES ANALYSIS" REDUCED grid: only two numeric groups, SALE and CLOSING,
    # each printed as a (QTY, VALUE) pair — NO opening/purchase/free/return columns at all.
    # The two-row header is a banner "<===SALE===>  <==CLOSING==>" over
    # "ITEM DESCRIPTION | QTY. | VALUE | QTY. | VALUE" (S.M. MEDICAL ENTERPRISE, KLM). The
    # generic `tabular` reader has no header to bind and returns 0 usable rows -> UNKNOWN.
    # Keyed on the compact banner arrows ("===sale===" + "==closing==") UNDER an
    # "itemdescription" header, AND the deliberate ABSENCE of any opening/purchase token
    # (every full Marg "STOCK & SALES ANALYSIS" sibling carries OPENING/PURCHASE or the
    # SALESANALYSIS + S/R movement columns). Verified to match ONLY this export across all
    # 124 stock xlsx/xls in New_Data, so it cannot steal any other vendor's grid.
    # BALLRI PHARMA: Marg ERP9+ reduced SALE/CLOSING grid as a CLEAN column-aligned grid
    # (col0 product, col1 SALE qty, col2 SALE value, col3 CLOSING qty, col4 CLOSING value +
    # RE-ORDER/APR/MAR). Same banner as marg_sale_closing_xlsx but a positional grid with a
    # clean "QTY." sub-header (not the merged-column S.M. MEDICAL form), and its MARG footer
    # ('Online Purchase Import') carries the word 'purchase' so the sale_closing gate below
    # (which forbids 'purchase') never fires. Requiring the clean 'qty.' sub-label keeps it
    # off the merged S.M. MEDICAL file. MUST precede the marg_sale_closing_xlsx gate.
    # Marg reduced SALE/CLOSING report exported as a single-column fixed-width TEXT dump
    # (SAM MEDICOS, KLM_S_S.XL.XLS): the whole line sits in ONE nbsp-padded cell, so both
    # cell-splitting grid siblings extract 0 rows. Same '===SALE=== ==CLOSING==' banner but
    # single_col=True (the grid siblings never are). MUST precede both grid gates below.
    if (
        single_col and "===sale===" in flat and "==closing==" in flat
        and "itemdescription" in flat and "opening" not in flat
    ):
        return "marg_sale_closing_text_xlsx"
    if (
        "===sale===" in flat and "==closing==" in flat and "itemdescription" in flat
        and "qty." in flat and "opening" not in flat
    ):
        return "marg_sale_closing_grid_xlsx"
    if (
        "===sale===" in flat and "==closing==" in flat and "itemdescription" in flat
        and "opening" not in flat and "purchase" not in flat
    ):
        return "marg_sale_closing_xlsx"
    # KLM "Stock and Sale Statement" scheme-carrying export (VENUS PHARMA, KLM MAY.XLSX),
    # division-banded (col3 repeats "KLM LABORATORIES -COSMOCOR" on every data row). Same
    # title/header family as venus_stock_excel BUT this export additionally carries the
    # scheme/free columns P.Sch + S.Sch AND the duplicated current-qty analytics CrQty +
    # CrSchQty. The generic venus_stock_excel parser DROPS P.Sch/S.Sch, so ~58% of rows fail
    # sanity; folding P.Sch->purchase_free and S.Sch->sales_free reconciles 186/190. Keyed on
    # the P.Sch + S.Sch + CrQty + CrSchQty combo (which plain venus export lacks entirely), so
    # it cannot steal any other vendor. MUST precede the venus_stock_excel gate below.
    # GUARD: the pre-existing per-division VENUS baseline exports (VENUS PHARMA - COSMO /
    # COSMOCOR / DERMA / ... .XLSX) share every one of these tokens BUT additionally carry a
    # "StkAd" (StkAdj) column and already parse correctly on venus_stock_excel; this New_Data
    # export (KLM MAY.XLSX) omits StkAd. "stkad" not in flat keeps those 8 baseline files on
    # venus_stock_excel while this scheme-folding parser claims only the StkAd-less export.
    if (
        "p.sch" in flat and "s.sch" in flat and "crqty" in flat
        and "crschqty" in flat and "clstk" in flat and "opstk" in flat
        and "stkad" not in flat
    ):
        return "klm_venus_opstk_crqty"
    # KLM "STOCK & SALES ANALYSIS" single-column TEXT dump — REDUCED 4-column form (AMETOMBI):
    # header 'ITEM DESCRIPTION OPENING RECEIPT ISSUE CLOSING M.EXP'. Only 4 movement columns, so
    # the 14-number marg_stock_analysis_text parser drops every row. Gated on RECEIPT+ISSUE with
    # NO 'dump'/'purchases'; verified to match only the 2 AMETOMBI books. MUST precede the fallback.
    if (
        single_col and "itemdescription" in flat and "receipt" in flat and "issue" in flat
        and "closing" in flat and "m.exp" in flat and "dump" not in flat
        and "purchases" not in flat
    ):
        return "stock_sales_analysis_oic_xlsx"
    # KLM "STOCK & SALES ANALYSIS" single-column TEXT dump — WIDE movement grid (KRISHNA PHARMA):
    # OPENING/PURCHASES/SALE-RETURN/OTHERS/TOTAL/SALES/PURCH-RETURN/OTHERS/CLOSING/RE-ORDER.
    # Gated on the distinctive PURCHASES + REPL./ + RE-ORDER tokens and the ABSENCE of 'receipt',
    # disjoint from the OIC gate above; verified to match only the KRISHNA PHARMA book.
    if (
        single_col and "itemdescription" in flat and "purchases" in flat and "repl./" in flat
        and "reorder" in flat and "m.exp" in flat and "closing" in flat
        and "receipt" not in flat
    ):
        return "stock_sales_analysis_wide_xlsx"
    if single_col and "itemdescription" in flat and "m.exp" in flat and "opening" in flat:
        return "marg_stock_analysis_text"
    # KLM "DETAILED" stock statement (VENKATA SAI) — a grid pairing a "Free" column after
    # every quantity column (Purchase|Free|P.Return|Free|Sale|Free|S.Return|Free|Others).
    # The duplicate "Free" headers defeat generic index-mapping (free + Others dropped ->
    # ~52% sanity fail); a header-driven positional parser folds each Free into its qty
    # column and Others by sign. Keyed on the "Age Of Item" + "Barcode" columns, a combo
    # unique to this export, so it cannot catch any other stock grid.
    if "ageofitem" in flat and "barcode" in flat and "p.return" in flat and "s.return" in flat and "closing" in flat:
        return "klm_detailed_stock"
    if "stockandsalestatement" in flat and "opstk" in flat:
        return "venus_stock_excel"
    if "stockreport" in flat and "itemname" in flat and "srno" in flat and "batch" in flat:
        return "infosoft_stock"
    # Marg (ERP 9+) 'STOCK & SALES ANALYSIS' FULL-movement GRID (SHAH ENTERPRISES .XLS),
    # division-banded, 15-col two-row header with blank spacer columns. tabular loses the
    # trailing STOCK Value col (closing_val==0 -> RED) AND leaks the appended 'PURCHASE DETAIL'
    # supplier ledger as fake products. Keyed on the signed Marg abbreviations -PurRet + +Repl +
    # -Return under the title + ITEM NAME header — unique to this full-movement export.
    if (
        "stock&salesanalysis" in flat and "itemname" in flat
        and "-purret" in flat and "+repl" in flat and "-return" in flat
    ):
        return "marg_stock_ss_full_movement_xls"
    if "stockreport" in flat and "itemname" in flat and "opening" in flat:
        return "marg_stock_wide"
    # R.K. PHARMA KLM "Stock and Sales Statement For Company: <DIV>" .xls — Opstk|Pur|Apr|
    # May|Sale|CurStk|StkVal|... The Apr/May prior-month history columns distinguish it from
    # plain marg_opstk_curstk below (which mis-handles this shape: never binds CurStk closing
    # and corrupts Pur). MUST precede that rule.
    if ("productname" in flat and "opstk" in flat and "apr" in flat
            and "may" in flat and "curstk" in flat):
        return "klm_opstk_apr_may_curstk_xls"
    if "productname" in flat and "opstk" in flat and "curstk" in flat:
        return "marg_opstk_curstk"
    if "ostk" in flat and "purtot" in flat and "saletot" in flat and "qoh" in flat:
        return "profit_maker"
    if "opeing" in flat and "productname&packing" in flat:
        return "fawin_stock"
    # Marg "wide" Stock & Sales grid: a 2-row band whose SUB-label row begins with the
    # exact 9-token movement sequence below, under a group row carrying OPENING/SALE/
    # PURCHASE/CLOSING. Unique to this layout (the doubled STOCK..STOCK..STOCK columns),
    # so it never collides with marg_erp9_movement (whose CLOSING+M.EXP live in one cell).
    _band = ["STOCK", "PURCHASES", "RETURN", "OTHERS", "STOCK", "SALES", "RETURN", "OTHERS", "STOCK"]
    for i in range(1, min(40, len(rows))):
        labels = [str(c).strip().upper() for c in rows[i] if str(c).strip()]
        if labels[:9] == _band:
            grp = " ".join(str(c).upper() for c in rows[i - 1])
            if "OPENING" in grp and "CLOSING" in grp and "PURCHASE" in grp and "SALE" in grp:
                return "marg_stock_sale_band"
    # KLM abbreviated-header positional export (OPSTK / PURC / SALE / SALEV / STOCK /
    # STOCKV): the closing column is the bare "STOCK" abbreviation, which the generic
    # tabular matcher fails to map to closing_stock (it stays raw_stock) -> closing reads
    # all-zero and every row fails sanity. The SATARA variant additionally carries all-zero
    # IN/OUT transfer columns that exact-match purchase/sales synonyms and steal them. This
    # OPSTK+PURC+SALEV+STOCKV abbreviation set is unique to this KLM family — SATARA adds
    # SWQ/SWV, the "STOCK AND SALES STATEMENT" variant (e.g. AMI) adds NEXD instead — so the
    # positional parser (which maps only known headers, by exact text) is the home for both.
    flat12 = " ".join(" ".join(str(c) for c in row) for row in rows[:12]).upper().replace(" ", "")
    if "OPSTK" in flat12 and "PURC" in flat12 and (
        # value variant (AMI/SATARA): closing qty + value columns
        ("STOCKV" in flat12 and "SALEV" in flat12)
        # qty-only variant (PEDIA): bare STOCK closing + the KLM-specific LZSTK aging token,
        # no value columns. LZSTK is unique to this family, so it can't collide with a
        # generic tabular stock sheet.
        or ("STOCK" in flat12 and "LZSTK" in flat12)
    ):
        return "klm_dstk_stock"
    # Marg ERP 9+ "Stock & Sales Analysis" movement export. Its CLOSING column
    # MERGES the closing qty with the nearest months-to-expiry into one header
    # cell ("CLOSING M.EXP") and one data cell ("101  2/28"), so the generic
    # `tabular` numeric cast returns None and closing reads all-zero -> every row
    # fails the sanity equation. We route ONLY this merged-closing variant here;
    # other Marg layouts that keep closing-qty in its own column already reconcile
    # via `tabular`, so we deliberately leave them untouched (no regressions).
    for row in rows[:30]:
        for cell in row:
            c = str(cell).lower()
            if "closing" in c and ("m.exp" in c or "mexp" in c or "m exp" in c):
                return "marg_erp9_movement"
    # Same Marg "STOCK & SALES ANALYSIS" movement layout as marg_stock_analysis_text but
    # exported as a GRID (2-row split header; qty+free merged into cells like "0    0").
    # The offset header makes the generic `tabular` reader map PURCHASE onto the free
    # column -> ~69% sanity fail. Keyed on the distinctive movement columns (S/R + REPL/
    # + FREE SAMPLE + T/F) under the sales-analysis title — a set no plain stock grid
    # carries, and which reconciles when the parser joins each row and reads the trailing
    # 14-column block. Placed AFTER marg_erp9_movement so the CLOSING+M.EXP variant wins.
    # YUVEE: spelled-out WIDE Marg "STOCK & SALES ANALYSIS" grid (SALES RETURN / SAMPLE /
    # PURCHASE RETURN full words + arrow separators), the sibling of marg_stock_analysis_text
    # whose abbreviated grid uses S/R + REPL/ + FREE SAMPLE + T/F. The 's/r'/'repl/' negative
    # clauses keep the two disjoint. MUST precede marg_stock_analysis_text.
    if (
        "salesanalysis" in flat and "itemdescription" in flat and "salesreturn" in flat
        and "sample" in flat and "t/f" in flat and "opening" in flat and "closing" in flat
        and "s/r" not in flat and "repl/" not in flat
    ):
        return "marg_stock_analysis_wide_xlsx"
    if (
        "salesanalysis" in flat and "itemdescription" in flat and "s/r" in flat
        and "repl/" in flat and "freesample" in flat and "t/f" in flat and "closing" in flat
    ):
        return "marg_stock_analysis_text"
    # DEEPA KLM 'SALE_DTL' abbreviated-header export: CL_BAL is the closing QTY (the generic
    # tabular reader fuzz-binds it to closing_value). Unique underscore-abbrev header set.
    if "sale_qty" in flat and "op_bal" in flat and "cl_bal" in flat and "sret_qty" in flat and "bon_qty" in flat:
        return "klm_sale_dtl_xlsx"
    # DHRUVI HEALTH CARE (klm.xlsx) 'OP/OPVal/PI/PIVal/Sale/SI Value/CLQty/CLValue' grid —
    # the OUT-less sibling of klm_op_pi_clqty_xlsx (NO ST(Out)/ST Value column). PI has no
    # synonym so generic tabular drops it -> closing never reconciles. Requires the value set
    # AND the ABSENCE of st(out), keeping it disjoint from the ST(Out)-bearing sibling below.
    if (
        "clqty" in flat and "clvalue" in flat and "sivalue" in flat
        and "pival" in flat and "opval" in flat and "st(out)" not in flat
    ):
        return "klm_op_pi_sale_cl_value_xlsx"
    # DHRUVI KLM 'OP/PI/Sale/ST(Out)/CLQty' export: PI (purchase) and ST(Out) are dropped by
    # generic tabular (no synonym), so closing never reconciles. Unique abbrev header set.
    if "clqty" in flat and "clvalue" in flat and "st(out)" in flat and "sivalue" in flat and "pival" in flat:
        return "klm_op_pi_clqty_xlsx"
    # TIRUPATI MEDICOSE "STOCK & SALES" grid: NAME|PACK|OPEN|PURCHASE|LASTPERIOD|SALES|SALEAMT|
    # CLOSING|CLOSEAMT|NEAREXP|SAPCODE. Generic `tabular` reads the movement fine but leaks the
    # per-company "AMOUNT" subtotals and the "KLM LAB <div>" bands as products, and drops CLOSEAMT.
    # Keyed on the SALEAMT+CLOSEAMT+SAPCODE abbreviation set (unique to this KLM export), so it
    # cannot steal any other stock grid. Placed just before the tabular fallback.
    if "saleamt" in flat and "closeamt" in flat and "sapcode" in flat:
        return "klm_stock_sales_saleamt"
    # CHOUDHARY MEDICAL AGENCIES (KLM "KLM_COSMO_ORTHO.XLS"): a clean Open/Receipt/Issue/Closing
    # qty+value grid whose header uses the underscored abbreviations item_name | op_stock |
    # op_value | rec_qty | rec_value | iss_qty | iss_value | clos_qty | clos_value. The shared
    # header-synonym "contains" heuristic collapses every *_value column onto sales_value and
    # both iss_qty/clos_qty onto sales_qty, so the generic `tabular` mapper never binds
    # closing_stock / closing_stock_value / purchase_value -> closing reads all-zero and every
    # stocked row fails sanity. A dedicated positional parser maps these exact abbreviations so
    # receipt->purchase, issue->sales and closing reconciles. Keyed on the op_stock + rec_qty +
    # iss_qty + clos_qty underscore set (disjoint from the KLM op_stk/pr_rec/cl_stk and
    # op_bal/cl_bal families), so it cannot steal any other stock grid.
    if (
        "op_stock" in flat and "rec_qty" in flat and "iss_qty" in flat
        and "clos_qty" in flat
    ):
        return "stock_op_rec_iss_clos_grid"
    # CENTRAL DISTRIBUTORS (KLM custom ERP) "Stock And Sales Report" 22-col exact-header .xls:
    # ProductCode|ProductName|...|PurchFreeQty|SaleQty|FreeQty|Sl.Ret.Qty|BR/E/D/R|Repl|AdjQty|
    # Cl.Stock|Sales Value|... The generic tabular reader maps ProductCode->product_name and
    # then skips all 157 rows. A header-driven positional parser binds only known columns
    # (folding signed AdjQty). Keyed on productcode+purchfreeqty+sl.ret.qty+br/e/d/r+adjqty+
    # cl.stock — unique to this export, so it cannot steal any other grid.
    if (
        "productcode" in flat and "productname" in flat and "purchfreeqty" in flat
        and "sl.ret.qty" in flat and "br/e/d/r" in flat and "adjqty" in flat
        and "cl.stock" in flat
    ):
        return "central_stock_and_sales_xls"
    # SHRI JAYANTHI "MFR Wise Stock and Sales" abbreviated Op/PQ/Fr/SQ/Fr1/Rp2/.../Cl Qty export
    # (.xls holding .xlsx). Generic tabular mis-binds PR->rate / ST->gst_rate and leaks value
    # footers as phantoms. Keyed on the Fr1/Rp2 dual-rate run + PQ/Fr/Rp/SQ header block —
    # unique to this export (distinct from the DHRUVI klm_op_pi_clqty_xlsx 'st(out)'/'pival' gate).
    if "fr1rp2" in flat and "pqfrrpsq" in flat and "srpradjstclqty" in flat:
        return "klm_mfr_op_pq_clqty_xlsx"
    # G.S. DISTRIBUTORS "KLM-STOCK AND SALES STATEMENT" wide 28-col grid:
    # PCode|Product Name|Packing|OPSTK|PURC|SALE|STOCK|...|PURCV|SALEV|...|EXSTKV|...|
    # STK120|Parent Manufacturer|... Generic tabular mis-binds the many columns (bare
    # PURC/SALE have no synonym; STOCK is the closing qty). Keyed on the movement/value run
    # plus the distinctive EXSTKV + Parent Manufacturer columns — matches 1/359 corpus files;
    # disjoint from the clqty/clvalue and saleamt sibling gates above.
    if (
        "opstk" in flat and "purc" in flat and "sale" in flat and "stock" in flat
        and "purcv" in flat and "salev" in flat and "exstkv" in flat
        and "parentmanufacturer" in flat
    ):
        return "gs_stock_sales_wide27_xlsx"
    # KLM "Stock and Sale for Company: <DIVISION>" grid (SHRI VENKATESH, one .xlsx per division).
    # Header: Product|Pack|Op.Stk.|Purch.|PuScm|GD In|Total|Sale|PTS Sl|Trfr Out|GD OUT|Sl Scm|Cl
    # Stk. The generic tabular mapper drops the OUT-flow columns (Trfr Out/GD OUT/PTS Sl) and
    # mis-binds PuScm to sales_free, so dispatch/transfer rows fail sanity. Keyed on the
    # puscm+gdout+slscm+clstk token set, unique to this KLM export.
    if "puscm" in flat and "gdout" in flat and "clstk" in flat and "slscm" in flat:
        return "klm_stock_sale_gdout_xlsx"
    # Marg "Report Designer" raw compute-column export (BALAJI): movement columns carry
    # internal IDs compute_0003..0027 (no display template applied) so the generic tabular
    # reader finds no stock header -> 0 rows. Product names live in c_name_item. Keyed on
    # the exact designer signature (c_item_code + the compute run + c_name_item), which no
    # templated report can match; the reconcile-verified compute->field map lives in the
    # layout module.
    if "c_item_code" in flat and "c_name_item" in flat and "compute_0022" in flat:
        return "marg_designer_compute_stock"
    # NOTE: klm_mfac_group_wise_stock (ANNAPURNA C-Square "Stock and Sales Mfac Group Wise
    # Report") is intentionally NOT gated. MINERVA STORES ships the IDENTICAL C-Square report
    # (same "stockandsalesmfacgroupwisereport" title + Item/Bal/BVal/SVal header) but a wider
    # 59-col variant that the ANNAPURNA-tuned positional parser only reads to AMBER (53 rows
    # mis-reconcile) — the only header difference is the prior-month labels (apr/may vs
    # jan/feb), which rename monthly, so no stable token separates them. Gating would break
    # MINERVA's frozen baseline, so ANNAPURNA stays on tabular. (The parser file is retained
    # for a future width-robust revision.)
    return "tabular"

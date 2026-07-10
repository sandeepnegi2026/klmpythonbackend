import re


def detect_layout(text, n_rects):
    low = text[:3000].lower()
    # MediVision Platinum "Stock and Sales" report (SIND DISTRIBUTORS). Adobe-UTF-8
    # CID export: pdfminer can't map its glyphs, so pdf_io falls back to PyMuPDF and
    # the parser re-reads word x-coords via fitz (right-aligned numbers, blank cells).
    # "medivision" + "stock and sales" + "companies:" is unique — cannot steal any
    # other vendor; MUST precede the coarse "stock and sales" -> simple4 rules below.
    if "medivision" in low and "stock and sales" in low and "companies:" in low:
        return "medivision_stock_sales"
    if "liquidation" in low and "sh.exp" in low:
        return "dolphin_stock"
    if "opstk" in low and "purch" in low and "in/ot" in low:
        return "toreo_stock"
    if "hos.sales" in low and "lms" in low:
        return "kluster_stock"
    # PharmAssist (C-Square) 'Stock and Sales Mfac Group Wise Report' — glyph-interleaved
    # text needs positional (x-coordinate) parsing. Title token is unique to this export.
    if "mfac group wise" in low:
        return "pharmassist_mfac"
    # Marg qty-only 'Stock and Sales' group-wise report (BASHA, KAMAKSHI): 4 qty
    # columns Opening Qty / Recd.Qty / Issued Qty / ClsQty with blank interior cells
    # and a header value-totals block. 'recd.qty'+'clsqty' is unique to this export;
    # it must precede the coarse stock_simple_7col / simple4 rules (whose loose word
    # tests match the header value block) — needs a positional parser (blank cells).
    if "recd.qty" in low and "clsqty" in low:
        return "marg_stock_recd_issued"
    # CENTRAL AGENCIES (BlueFox) "Stock And Sales Report" — dense 14-column text
    # table banded by "KLM <DIV>". Gate on the report title + the unique 'BR/E'
    # (Return Breakage/Expiry) column + the compact 'Sale Value F.Value Qty Bal.Val'
    # header tail; this token set appears in no other stock layout, so it can only
    # catch these files (which otherwise fall through to 'generic' and lose every
    # comma-grouped value row). FATIMA HEALTHCARE ships the identical BlueFox
    # export titled "Stock And Sales from <date> to <date>" (no "Report"), hence
    # the second title form — still gated by both unique header tokens.
    _c_central = low.replace(" ", "")
    if (
        ("stockandsalesreport" in _c_central or "stockandsalesfrom" in _c_central)
        and "br/e" in _c_central
        and "salevaluef.valueqtybal.val" in _c_central
    ):
        return "central_stock_sales"
    # Medicine Traders (Ajmer) SwilERP "Sales & Stock Statement": PRODUCT NAME | PACKING
    # | Op.Bal. | Receipt | Free Q | Total | Issue | Free Q | Closing. Two separate Free-Q
    # columns (receipt-free inflow, issue-free outflow) around a printed Total cross-check,
    # so the coarse simple4 (opening/receipt/issue/closing) rule below mis-maps the Total /
    # Free-Q cells. Each row carries exactly 7 trailing numbers; a flat token parse pops
    # them cleanly. The report title "sales & stock statement" plus the compact doubled
    # header run "freeqtotalissuefreeqclosing" is unique to this SwilERP export and appears
    # in no other stock layout, so it cannot steal other vendors. MUST precede the coarse
    # simple4 / op.bal. rules below.
    _comp = low.replace(" ", "")
    if "sales & stock statement" in low and "freeqtotalissuefreeqclosing" in _comp:
        return "medtraders_sales_stock_statement"
    # B.M. PHARMACEUTICALS (Bhubaneswar) SwilERP "Sales & Stock Statement": a mid-band
    # LastPurc DATE column sits between Receipt and Total (Op.Bal|Receipt|LastPurc|Total|
    # Issue|Closing|Dump), so the coarse simple4 rule halts its trailing-number pop at the
    # dd/mm/yy token and mis-maps Total/Issue/Closing/Dump. 'lastpurc' is unique to this
    # SwilERP export; distinct from the medtraders sibling above (two Free-Q cols, no
    # LastPurc). MUST precede the coarse simple4/op.bal rules below.
    if "sales & stock statement" in low and "lastpurc" in low:
        return "swil_stock_lastpurc"
    # BIDYA PHARMA SwilERP "Sales & Stock Statement": the richest column set of the
    # family — it breaks out TRANSFER-IN (Transin) and TRANSFER-OUT (TranOut) stock
    # movements, with a Qty+Value pair per measure (Op|Receipt|Transin|Total|Issue|
    # TranOut|Closing|Dump|Near). Its header carries "opening bal"+"receipt/pur"+
    # "issue/sales"+"closing bala", so the coarse qty_value_total rule below claims it
    # and mis-maps the 7 Qty/Value pairs -> 100% false SANITY_FAILED. The tokens
    # 'transin'/'tranout' are unique to this export (absent from the lastpurc and
    # medtraders siblings, which are gated above), so this gate cannot steal them, and
    # it MUST precede the qty_value_total rule. Reconcile folds Transin -> purchase_free
    # (inflow) and TranOut -> sales_free (outflow): closing = Op+Rec+Trin-Iss-TrOut.
    if "sales & stock statement" in low and "transin" in low and "tranout" in low:
        return "swil_stock_transfer"
    # DEEPA(A) AGENCIES dot-matrix "STOCK AND SALES STATEMENT" (KLM): header run
    # OPEN/REC-/ADJ(-)/ADJ(+)/TOTAL/SALES/CLOSE/ORD.QTY. 'ORD.QTY' + the 'REC- ADJ ADJ'
    # run appear in no other stock layout; without this gate the coarse simple4 rule below
    # steals it and mis-maps ADJ(-)/ADJ(+) into sales/closing.
    if "openrec-adjadjtotalsalescloseord.qty" in _comp and "stock and sales statement for the month of" in low:
        return "stock_open_rec_adj_close"
    # CHAMPAVATI PHARMA LLP (GAJANAN ENT., BEED) 'Stock and sales Statement': KLM ERP with
    # the ERP's own MISSPELLED header 'Purticular Pkg. Open. Purch. Sales Ret. Sales & DC
    # Misc. Out Close Stock Closing Value Sales Value'. Six qty cols + two rupee cols; the
    # coarse simple4 rule maps only the first 4 of the 8-token tail. 'purticular' is unique
    # (NOT 'particulars', the swastik token), so no collision either direction.
    if "purticular" in low and "misc." in low:
        return "stock_open_purch_miscout"
    # KLM (custom KLM ERP) "CLOSING STOCK REPORT FROM .. TO .." — one file per
    # COMPANY/division (KAPOOR MEDICAL STORE: KLM COSMO / COSMO COR / COSMO Q /
    # DERMA / DERMA COR / PHARMA / GYNAE). Flat table, NO party column; fixed
    # cols SNO|ITEM NAME|PACKING|OP STK|PUR QTY|PUR VALUE|SALE QTY|SALE VALUE|
    # FREE|CL STOCK|CLOSING VALUE with RIGHT-ALIGNED, blank-interior cells that
    # give a VARIABLE trailing-number count, so it needs a positional (word
    # x-position) parser. Gate on the compacted body signature: the report title
    # "closingstockreport" + the glued header run "freeclstock" (FREE CL STOCK) +
    # "closingvalue" + "salevalue" — this token set is unique to this KLM export
    # and appears in no other stock layout, so it cannot steal other vendors.
    # MUST precede the coarse n_rects rules below: pharma.pdf has 410 rects and
    # would otherwise be grabbed by the "n_rects > 400 -> marg_bordered" rule.
    _comp = low.replace(" ", "")
    if (
        "closingstockreport" in _comp
        and "freeclstock" in _comp
        and "closingvalue" in _comp
        and "salevalue" in _comp
    ):
        return "klm_closing_stock_report"
    # Marg "STOCK & SALES ANALYSIS" reduced SALE/CLOSING report — S.M. MEDICAL
    # ENTERPRISE variant. Same banner family as stock_sale_closing_pairs
    # (<===SALE===> <==CLOSING==>, ITEM DESCRIPTION QTY. VALUE QTY. VALUE, exactly
    # 4 SALE/CLOSING numbers per row, no opening/purchase/free columns), BUT this
    # vendor (a) sells genuine products named "KLM D3/FX/KLIN/AHA/C 20" that the
    # shared _skip_line in stock_sale_closing_pairs eats (dropping ~21 rows, -8.7%
    # of the sale total), and (b) appends a supplier/purchase register at the tail
    # that must be excluded. The dedicated parser fixes both. The division band
    # "KLM LABORATORIES PVT.LTD(" (compact 'klmlaboratoriespvt.ltd(') appears in
    # this export's first page and is ABSENT from the SRI RAGHUNATH file that must
    # stay on stock_sale_closing_pairs, so it cannot steal that vendor; requiring
    # opening/receipt/issue ABSENT keeps it off the 4-group oric/simple4 exports.
    # MUST be placed ABOVE the stock_sale_closing_pairs rule.
    _comp = low.replace(" ", "")
    if (
        "<==closing==>" in _comp
        and "<===sale===>" in _comp
        and "stock&salesanalysis" in _comp
        and "klmlaboratoriespvt.ltd(" in _comp
        and "opening" not in low
        and "receipt" not in low
        and "issue" not in low
    ):
        return "marg_sale_closing_pdf"
    # Marg (KLM) "Stock and Sale Report" (SRI SENTHIL MEDICAL AGENCIES):
    # Product Name|Pack|OpStk|Purch|PrvSa|Sales|Adj|Cl.St|P.price|Sales Valu|Age.
    # Interior qty cells (PrvSa/Sales/Adj/Cl.St) blank out for no-movement rows,
    # collapsing the flat-text index, so this needs a positional (x-binning) parser.
    # Gate on the unique token "prvsa" together with the "stock and sale report"
    # title + "opstk"; "prvsa" appears in NO other stock layout so it cannot steal
    # other vendors, and it distinguishes this from the sibling marg_opstk_statement
    # ("Stock and Sale Statement", no PrvSa). Must precede that rule and the coarse
    # "stock & sales"->simple4 fallback below.
    if "stock and sale report" in low and "opstk" in low and "prvsa" in low:
        return "klm_stock_sale_prvsa"
    # Marg/KLM PALANPUR "MONTHLY STOCK & SALES STATEMENT" (AAKASH DISTRIBUTORS):
    # Code | * | Product | Pack | Opening | Purchase | Goods Ret. | Total In |
    # Sale | Purc. Ret. | Balance | Order 1 (Qty/Free) | Order 2 (Qty/Free) | Remarks.
    # Right-aligned cols with collapsed blank interiors -> needs a positional parser.
    # The compact column-header run "goodstotalsalepurc.ret.balance" plus the
    # "order1order2remarks" trio is unique to this export; gate on both (spaces
    # stripped) so it cannot steal any other vendor's statement.
    _comp = low.replace(" ", "")
    if "goodstotalsalepurc.ret.balance" in _comp and "order1order2remarks" in _comp:
        return "marg_monthly_ss_statement_pdf"
    # KLM 'Stock Report' with dual sales columns (SAI PHARMA, SANGAMNER): Item Name |
    # Packg | Open.Stk. | Receipt | L.Sales | Cur.Sls | Pur.Rtn | Sls.Rtn |
    # Clos.(Qty & Amt). The last header cell covers TWO physical columns (closing QTY
    # then closing VALUE), so the generic/simple4 parser mis-reads the rupee value into
    # closing_stock. Only Cur.Sls is the current outflow (L.Sales is prior-month,
    # informational). The glyph-merged compact header tail is unique to this export;
    # a POSITIONAL x-position parse is required (fixed-width text export, n_rects==0).
    if "cur.slspur.rtnsls.rtnclos.(qty" in low.replace(" ", ""):
        return "stock_open_rcpts_dualsales_pdf"
    # KLM 'Stock And Sales Report(Month)' — one report per division (YOGIRAM
    # PHARMA). Numeric cells are printed BLANK for zero-movement products and the
    # numbers are glyph-interleaved/right-aligned, so it needs a positional
    # (x-coordinate) parser. The report title compacted to 'stockandsalesreport(month)'
    # plus the exact glued header run 'opstpursalefreeadjcl.s' is unique to this KLM
    # export, so this gate cannot steal any other vendor's stock file. Must precede
    # the coarse n_rects / simple4 rules below.
    # KLM 'Stock And Sales Report(Month)' RepQ dialect (JEYANTHI PHARMAA): same per-division
    # export family as klm_stock_sales_month but a different column vocabulary — header
    # 'ProductName Pack OpSt PurQ Mar Apr Sale Free RepQ SaleValue Stock StockValue LPD'.
    # Blank zero-cells + mixed left/right alignment => positional parser. 'repq'/'stockvaluelpd'
    # appear in no other gate; the sibling below requires 'opstpursalefreeadjcl.s' which this
    # dialect lacks (mutually exclusive). MUST precede the sibling.
    _comp_repq = low.replace(" ", "")
    if ("stockandsalesreport(month)" in _comp_repq and "opstpurq" in _comp_repq
            and "repqsalevalue" in _comp_repq and "stockvaluelpd" in _comp_repq):
        return "klm_stock_sales_month_repq"
    compact = low.replace(" ", "")
    if "stockandsalesreport(month)" in compact and "opstpursalefreeadjcl.s" in compact:
        return "klm_stock_sales_month"
    # Saleable Stock Report (SURANA DRUG DISTRIBUTORS): pipe-delimited text PDF,
    # header "Saleable Stock Report" with Opn/Rec/Issue/Bal columns sub-labelled
    # "(Q+F)". The header uses abbreviations (Opn/Rec/Bal), so the coarse
    # opening/receipt/issue/closing family below never matches and it would fall to
    # generic. The compact "saleablestockreport"+"(q+f)" pair is unique to this
    # export (no other stock_pdf layout uses "saleable" or "(q+f)"), so it is
    # safe to gate high with zero risk of stealing other vendors.
    if "saleablestockreport" in low.replace(" ", "") and "(q+f)" in low.replace(" ", ""):
        return "saleable_stock_qf"
    # PharmAssist (C-Square) 'Stock and Sale Report' — SINGLE-PAGE wide variant
    # (DELTA PHARMA; one file per KLM division: COSMO/DERMA/PED/PHARMA...). The whole
    # column band prints on one page with a bare "Item Pack" header (NO Item Code/Item
    # Name), so the page-split gate below (which requires item code+item name) skips it,
    # and it lacks the literal 'name'/'purchase' header tokens for stock_simple_7col, so
    # it currently falls to 'generic' and mis-reconciles. The wide header carries the
    # unique 'BrBsc' column, which appears in NO other stock layout (the page-split
    # sibling uses a bare 'Br'), so gating on 'brbsc' + the 'Stock and Sale Report'
    # title + the 'PharmAssist' watermark cannot steal any other vendor. Blank interior
    # cells + glyph-interleaved name/pack -> needs a positional parser. MUST precede the
    # page-split gate and the coarse stock_simple_7col/generic rules below.
    if (
        "stock and sale report" in low
        and "pharmassist" in low
        and "brbsc" in low.replace(" ", "")
    ):
        return "pharmassist_stock_sale_single"
    # PharmAssist (C-Square) 'Stock and Sale Report' — HORIZONTAL PAGE-SPLIT sibling of
    # pharmassist_mfac. The column band is split across two physical pages per logical
    # "Page N of M": LEFT page = Item Code/Name/Pack/Apr/Mar/Op./Pur/SP/Sale/SVal/SS,
    # RIGHT page = Br/Cr/Db/Adj/Bal./BVal/Order. A flat text parse cannot see Bal. on the
    # left-block rows, so a positional (x-anchored) parser stitches the two pages by top.
    # Gate on the 'Stock and Sale Report' title + the 'PharmAssist' watermark + the unique
    # right-block header tokens (BVal + Order) so it CANNOT steal the mfac variant (whose
    # title is 'Stock and Sales Mfac Group Wise Report') or any other vendor. Must beat the
    # 'generic' fallthrough (this file currently detects as generic).
    _lc = low.replace(" ", "")
    if (
        "stock and sale report" in low
        and "pharmassist" in low
        # SWETA's page-split C-Square export carries a separate Item Code + Item Name +
        # Packing column set; the single-page C-Square siblings (BANERJEE, RSK) use a bare
        # "Item Pack" header and are handled correctly by stock_simple_7col/generic, so
        # requiring item-code+item-name keeps this gate from stealing them.
        and "item code" in low
        and "item name" in low
        and "bval" in _lc
        and "order" in _lc
    ):
        return "pharmassist_stock_sale"
    # Marg "STOCK & SALES ANALYSIS" reduced 2-group SALE/CLOSING qty+value pairs
    # (SRI RAGHUNATH MEDICAL "KLM ALL SALE / STOCK"). Grouped header
    #   <===SALE===>  <==CLOSING==>
    #   ITEM DESCRIPTION  QTY. VALUE  QTY. VALUE
    # Each row = product+pack + exactly 4 numbers (SALE_QTY, SALE_VALUE,
    # CLOSING_QTY, CLOSING_VALUE); opening/purchase/free columns are dropped by
    # this vendor. The compact "<==closing==>"+"<===sale===>" banner is unique;
    # requiring opening/receipt/issue to be ABSENT keeps it off the 4-group
    # stock_oric_pairs / simple4 / qty_value_total exports.
    _comp = low.replace(" ", "")
    if (
        "<==closing==>" in _comp
        and "<===sale===>" in _comp
        and "stock & sales analysis" in low
        and "opening" not in low
        and "receipt" not in low
        and "issue" not in low
    ):
        return "stock_sale_closing_pairs"
    # KLM own-vendor "Stock sales statement(Combined)" wrapped grid (VISION HEALTHCARE
    # HOLDINGS): Product Name|Pack|Rate|Prev.Sale|Opening|Purchase|Total Sale|Sale Value|
    # Adj.|Total Closing|Closing Value. This is a WRAPPED render of an .xlsx grid: numbers
    # are right-aligned and wrap their low-order digits onto continuation lines, so a
    # positional (word x-position) parser is required. The title "statement(Combined)"
    # plus the wrapped column set (compact 'totalclosing'+'closingvalue'+'totalsale') is
    # unique to this KLM export, so the gate cannot steal any other vendor's stock file.
    # Placed above all coarse rules (stock_simple_7col / simple4) which would otherwise
    # match on name/pack/open/purchase/closing.
    _compact = low.replace(" ", "")
    if (
        "statement(combined)" in _compact
        and "stocksalesstatement" in _compact
        and "totalclosing" in _compact
        and "closingvalue" in _compact
        and "totalsale" in _compact
    ):
        return "klm_stock_sales_combined_pdf"
    # Prompt ERP "Stock Statement (Datewise)" — free-carrying KLM variant (V.G.RAJA).
    # Same Prompt export as `prompt`, but the numeric sub-header carries dedicated
    # Pur.Free + Sales.Free columns plus a Sales Amount and a Closing Amount:
    #   "Qty  Qty Free  Qty Free mount  Qty Amount  A3Mn  E/E  Age"
    # The plain 7-col `prompt` mapping reads the closing *Amount* into closing_stock
    # here, so this 8-value-core variant needs its own positional parser. Gate on the
    # doubled Free + "mount"(Amount) geometry ("free ... mount qty amount") together
    # with the Prompt-specific A3Mn stat column, so plain 7-col Prompt files are NOT
    # stolen. Positional (blank interior cells + wrapped names) -> dedicated parser.
    if "a3mn" in low and "freemountqtyamount" in low.replace(" ", ""):
        return "prompt_dstk_free_pdf"
    # Marg 'STOCK & SALES ANALYSIS' movement detail — SPARSE (blank-omitted) variant
    # (AMIT MEDICOS / SHREE BALAJI / K.P.PHARMACEUTICALS). Same 10-column movement
    # header as marg_movement_detail, but the header terminates at RATE with NO M.EXP
    # / RE-ORDER column and the vendor OMITS zero cells (variable token count per row),
    # which the fixed-9 dense parser mis-aligns. The AHUJA dense family always appends
    # 'm.exp' (or 're-order'), so gating on the compact header 'othersstockrate' plus
    # the ABSENCE of m.exp/re-order isolates this variant. MUST precede the coarse
    # marg_movement_detail rule (which both variants' 'purchasesreturnothers' matches).
    if (
        "stock & sales analysis" in low
        and "othersstockrate" in low.replace(" ", "")
        and "m.exp" not in low.replace(" ", "")
        and "re-order" not in low
    ):
        return "marg_movement_detail_sparse"
    # Marg "Stock & Sales Statement Detailed" (SRI DURGA SRINIVASA PHARMA & VETS, KLM):
    # banded by "Company :KLM (<DIV>)"; one item row per line carrying a leading
    # item-code token, with 10 numeric columns O.Bal Purc S.Ret Total Sales P.Ret Total
    # ClBal Cl.Value Age. The Cl.Value column is rupees and must NOT land in a qty field,
    # so the coarse `stock & sales`->simple4 rule would mis-map it. The compact title
    # "stock&salesstatementdetailed" (or the O.Bal+Purc+S.Ret+ClBal+Cl.Value column set)
    # is unique to this export, so this must precede every coarse "stock & sales" rule.
    _compact = low.replace(" ", "")
    if "stock&salesstatementdetailed" in _compact or (
        "o.bal" in _compact
        and "purc" in _compact
        and "s.ret" in _compact
        and "clbal" in _compact
        and "cl.value" in _compact
    ):
        return "marg_ss_statement_detailed"

    # VIJAY MEDICAL "PRODUCT WISE STOCK AND SALE -WITH PROFIT" (Marg ruled
    # register): SNO | ITEM | PACK/SIZE | OPENING STOCK-1 | PURCHASE-1 |
    # NET SALE-1 | SALE VALUE TOTAL | CLOSING STOCK | CLOSING VALUE (PUR RATE)
    # with blank-when-zero interior cells -> positional right-edge parse.
    # The compact title is unique; MUST precede the coarse n_rects ->
    # marg_bordered rule below (the ruled page carries >400 rects).
    if "productwisestockandsale" in _compact and "profit" in _compact:
        return "product_wise_stock_sale_profit"
    if n_rects > 100 and "stock statement report" in low:
        return "marg_bordered"
    if n_rects > 100 and "product stock report" in low:
        return "marg_web_stock"
    if n_rects > 100 and "stock statement" in low:
        return "prompt_bordered"
    if n_rects > 400:
        return "marg_bordered"

    # --- KLM division stock statements: specific column structures, unique tokens ---
    # A.B.PHARMA-style monthly 'Stock Statment': Opening/Purchase/Stock-Out + N
    # month columns + Sales/Stock-In/Closing/Stock-Value/Sales-Value. The
    # hyphenated Stock-Out + Stock-In pair is unique to this export.
    if "stock-out" in low and "stock-in" in low:
        return "stock_in_out_statement"
    # SRI VASAVI 'STOCK AND SALES STATEMENT' batch-wise (Product|Packing|BATCH|EXP|Opening|
    # Receipts|Total|Sales|Closing Stock|Closing Value), one section per KLM division. The
    # BATCH+EXP column pair and doubled-Closing header run are unique; downstream marg_opstk/
    # klm_venus require the string 'stock and sale statement' (singular) which this file lacks.
    _comp_bws = low.replace(" ", "")
    if "stockandsalesstatement" in _comp_bws and "batchexpopeningreceiptstotalsalesclosingclosing" in _comp_bws:
        return "stock_batchwise_statement"
    # C.D. ASSOCIATES PROFITMAKER "Internal New" Qoh statement that ADDS explicit SRet/PRet
    # return columns (header 'Ostk Purc Sale SRet PRet Qoh QohValue') — a different column
    # order that the plain stock_qoh parser (O.Stk/Purc/Tot/Sale/Qoh/Value/Age) mis-maps
    # wholesale. Must precede the coarse `"qoh" in low` rule (these files also carry 'qoh').
    if "ostkpurcsalesretpretqohqohvalue" in low.replace(" ", ""):
        return "stock_qoh_returns"
    if "qoh" in low:
        return "stock_qoh"
    if "gd.in" in low:
        return "stock_gdin"
    if "amount-i" in low and "cl.stock" in low:
        return "stock_open_pur_sale_amt"
    if "op.bal." in low and "receipt" in low and "issue" in low and "shelf" in low and "msr" in low:
        return "disa_opbal_receipt_total_issue"
    # CAPITAL PHARMA AGENCIES (KLM) 'Sales & Stock Statement': clean five-qty layout
    # PRODUCT NAME | PACKING | Op.Bal. | Receipt | Total | Issue | Closing (Balance),
    # NO Shelf-ID/Tax-Rate/MSR columns (the DISA sibling above carries those and is
    # already claimed). Its title contains the substring "stock statement" and the body
    # has "product", so without this gate it falls through to the coarse "stock statement"
    # + "product" -> simple4 rule, which pops only the FIRST four of the five numbers
    # (Total -> sales_qty, Issue -> closing_stock) and DROPS the real Closing -> ~58%
    # false SANITY_FAILED. The compact header run "op.bal.receipttotalissueclosing" is
    # unique to this qty-only KLM export (DISA appends "msr-price"; medtraders/swil break
    # the run with "freeq"/"lastpurc"), so it cannot steal other vendors. Reconcile is
    # Closing = Op.Bal + Receipt - Issue (Total is the ignored Op+Receipt cross-check).
    if "op.bal.receipttotalissueclosing" in low.replace(" ", ""):
        return "capital_stock_sale_stmt"
    if "lstmove" in low:
        return "saraswati_lstsl"
    # SARASWATI 'Stock & Sales Report' 8-column variant WITHOUT the LstMove date
    # column: LstSL/Open/Recd/Sales/Close/Order/Pend/Stk.Value. saraswati_lstsl pops a
    # trailing Stk.Value then maps the LAST 7 stat cols, so it is correct ONLY for
    # this exact sequence — the 7-col (no Stk.Value) and 9-col (extra Issue) Micropro
    # siblings must stay on their existing (simple4) route. Gate on the exact compact
    # header signature so those siblings are not stolen.
    if "lstsl" in low and "salescloseorderpendstk.value" in low.replace(" ", ""):
        return "saraswati_lstsl"
    if "particulars" in low and "misc" in low:
        return "swastik_particulars"
    if "opqty" in low and "b_qty" in low:
        return "marg_opqty"
    if ("op.stk" in low and "sl/iss" in low and "cl.stk" in low) or (
        "op bal" in low and "pur" in low and "total" in low and "sales" in low and "cl bal" in low
    ) or (
        # NEW SINGH 'STOCK AND SALES ANALYSIS': full-word columns with a TOTAL
        # column between PURCHASE and SALE, plus three trailing value columns
        # (PUR.VALUE / SALE VALUE / CLOSING VALUE). The 'total'+'pur.value' pair
        # is specific to this export and keeps it off the coarse simple4 rule.
        "opening" in low and "purchase" in low and "total" in low and "sale" in low
        and "closing" in low and "pur.value" in low
    ):
        return "stock_op_pur_total_sale_close"
    if "received" in low and "issued" in low and "rplqty" in low:
        return "stock_received_issued"
    # marg sub-families: must beat the coarse marg_stock_long rule below
    if "replace+" in low or ("product description" in low and "opening" in low and "replace" in low):
        return "marg_pds_replace"
    if "opening purchase free sale free closing" in low:
        return "marg_open_pur_free_sale"
    if "stock & sales analysis" in low and "purchasesreturnothers" in low.replace(" ", ""):
        return "marg_movement_detail"
    # Marg 'STOCK & SALES ANALYSIS' full-movement variant (SIDDHIVINAYAK): 14 cols with
    # S/R, SAMPLE, P/R and a trailing M.EXP. That column set is unique to this export and
    # must beat the coarse marg_stock_long ("opening"+"sale"+"repl") rule below.
    if (
        "s/r" in low
        and "p/r" in low
        and "sample" in low
        and "m.exp" in low
        and "closing" in low
    ):
        return "marg_stock_analysis_full"
    # VISHWAKARMA MEDICAL AGENCY variant: the IDENTICAL 14-col STOCK & SALES ANALYSIS
    # full-movement layout (OPENING | PURCHASE Qty/Free | S/R | REPL/OTHER | TOTAL |
    # SALES Qty/Free | STOCK-OTHER | SAMPLE | P/R | REPL/OTHER | CLOSING) but WITHOUT the
    # trailing M.EXP column, so the m.exp gate above misses it and it falls to the coarse
    # marg_stock_long rule (which maps only opening/sale/repl -> 97% false SANITY_FAILED).
    # The S/R + P/R + SAMPLE movement set under a 'STOCK & SALES ANALYSIS' title is unique
    # to this Marg full-movement family; requiring the title keeps it off marg_stock_long
    # and the qty-only movement siblings (marg_movement_detail, gated above on
    # 'purchasesreturnothers', is unaffected — this header has 'purchase s/r repl', not
    # 'purchases return others'). Same parser handles both (M.EXP is optional there).
    if (
        "stock & sales analysis" in low
        and "s/r" in low
        and "p/r" in low
        and "sample" in low
        and "closing" in low
    ):
        return "marg_stock_analysis_full"

    if "stock statement" in low and "receipt" in low and "replace" in low:
        return "stock_receipt_replace"
    if "stock and sales report" in low and "issue qty" in low and "rcvd" in low:
        return "pharma_bytes_itemcode"
    if "opening" in low and "sale" in low and "repl" in low:
        return "marg_stock_long"
    if re.search(r"opening stock\s+<", low):
        return "marg_qty_value_wide"
    # Marg "STOCK SUMMARY": 8 qty/value movement groups (Opening, Purchases,
    # Pur. Returns, Receipts, Sales, Sales Return, Issue, Balance) with a Balance
    # Qty/Rate/Value triple + GST %. Far more specific than the value_pairs rule
    # just below (rate+opening+receipt/issue+value), so it must precede it.
    if (
        "purchases" in low
        and "pur. returns" in low
        and "receipts" in low
        and "sales return" in low
        and "issue" in low
        and "balance" in low
    ):
        return "marg_stock_summary"
    # NOTE: do NOT add a dedicated rule for the VIPIN "ITEM DESCRIPTION RATE
    # OPENING..CLOSING DUMP" qty+value PDF: the JINDAL/SHRIJI (M.EXP) and 5S
    # PHARMA exports share the same compact header but a different row shape,
    # and a 10-cell-pop parser regressed 15 working value_pairs files
    # (closing totals collapsed). value_pairs handles the family; VIPIN's two
    # digit-ending-name rows stay an honest AMBER.
    if (
        "rate" in low
        and "opening" in low
        and ("receipt" in low or "issue" in low)
        and "value" in low
    ):
        return "value_pairs"
    if "rate" in low and "qty value qty value" in low:
        return "nagendra_rate_pairs"
    if (
        "product" in low
        and "opening" in low
        and "purchase" in low
        and "lms" in low
        and "sales" in low
        and "closing" in low
    ):
        return "marg_lms_simple"
    if re.search(r"item name.*pack.*op\b.*pur\b.*sale\b.*c\s*stk", low):
        return "venus_stock_statement"
    if "stock and sales report" in low and "dec" in low and "jan" in low:
        return "venus_stock_statement"
    # KLM "Stock and Sales Statement": Sr | Code | Item Name | Packing | Opening |
    # Purchase | Sale | Free | Current | Sales Amount | Closing. Here the "Current"
    # column is the real closing QTY and "Closing" is the closing VALUE — the generic
    # stock_simple_7col rule below would map closing_stock <- Sales Amount. The Free +
    # Current pair is unique to this export, so this must precede stock_simple_7col.
    if (
        "item name" in low
        and "packing" in low
        and "opening" in low
        and "sale" in low
        and "free" in low
        and "current" in low
        and "closing" in low
    ):
        return "stock_open_pur_sale_free_current"
    if (
        "name" in low
        and "pack" in low
        and "open" in low
        and "purchase" in low
        and "closing" in low
    ):
        return "stock_simple_7col"
    if (
        "product" in low
        and "rate" in low
        and "open" in low
        and ("pur" in low or "purchase" in low)
        and "sales" in low
        and "amount" in low
        and "close" in low
    ):
        return "stock_rate_amount"
    if "item cd" in low and "item name" in low:
        return "dahod_marg"
    if (
        "opening bal" in low
        and "receipt/pur" in low
        and "issue/sales" in low
        and "closing bala" in low
    ):
        return "qty_value_total"
    if (
        "opening" in low
        and "receipt" in low
        and "issue" in low
        and "closing" in low
        and "qty. value qty. value" in low
    ):
        return "stock_oric_pairs"
    if "opening" in low and "receipt" in low and "issue" in low and "closing" in low:
        return "simple4"
    if "stock statement" in low and ("product" in low or "opening" in low):
        if "opening" in low and "purchase" in low and "lms" in low:
            return "marg_lms_simple"
        # Prompt 'Stock Statement (Datewise)' 4-pure-qty variant (DEV MEDICAL AGENCY):
        # OpStk|Pur|Sales|ClStk (all Qty) then an Amount column then A3Mn|Favourite.
        # Here ClStk is the closing stock; the base `prompt` mapping reads closing from
        # tail index 5, which in THIS export is the A3Mn (3-month avg qty) -> ~98% false
        # SANITY_FAILED. The 'Favourite' column is unique to this variant (no other Prompt
        # export carries it), so it cannot steal the base-prompt files. MUST precede the
        # base `prompt` rule below.
        if "opstk" in low and "a3mn" in low and "favourite" in low:
            return "prompt_datewise_favourite"
        if "opstk" in low and "pur" in low and "a3mn" in low:
            return "prompt"
        if "stock statement for company" in low and "pks data" in low:
            return "pks_data"
        return "simple4"
    if "monthly sales and stock" in low:
        return "saurashtra_monthly"
    if "monthly ss report" in low:
        return "saurashtra_ss_report"
    if re.search(r"item name.*pack.*op\b.*pur\b.*sale\b.*c\s*stk", low):
        return "venus_stock_statement"
    if "stock and sales report" in low and "dec" in low and "jan" in low:
        return "venus_stock_statement"
    # DAHOD PHARMAKON "Stock and Sale Statement" — SINGLE-PAGE glyph-interleaved sibling of
    # the Venus (klm_venus_opstk_crqty) export. Venus has the SAME columns but splits them
    # across two physical pages (…CrQty | CrSchQty ClStk ClVal Order), so in Venus text
    # "CrQty" and "ClStk" are never adjacent; DAHOD prints the whole band on one line, so
    # its compact header carries "crqtyclstkclval" contiguously (and it has NO CrSchQty).
    # The page-split klm_venus parser mis-reads DAHOD's single-page rows (closing lands
    # nowhere -> ClStk 0 -> false 100% SANITY_FAILED), so this MUST precede that rule.
    if ("stock and sale statement" in low and "opstk" in low
            and "crqtyclstkclval" in low.replace(" ", "")):
        return "dahod_stock_sale_stmt"
    # Venus KLM "Stock and Sale Statement" — a page-split, glyph-interleaved sibling of
    # marg_opstk_statement whose closing (ClStk/ClVal) is on a paired right page. It is
    # distinguished by the CrQty column AND the ABSENCE of a StkAd column (marg_opstk
    # carries StkAd); this gate must precede the marg_opstk rule below, which would
    # otherwise claim it and drop every closing value (false SANITY_FAILED).
    if ("stock and sale statement" in low and "opstk" in low
            and "crqty" in low and "stkad" not in low):
        return "klm_venus_opstk_crqty"
    if "stock and sale statement" in low and "opstk" in low:
        return "marg_opstk_statement"
    # MAHESH "Stock & Sales Report for the month": Product Name | Pack | LstSL |
    # Open | Recd. | Sales | Close | Order | Pend — exactly SEVEN stat cells, no
    # trailing Stk.Value. The extra LstSL column shifts the coarse simple4
    # mapping one cell left (opening<-LstSL, sales<-Recd.), so this must precede
    # the "stock & sales" -> simple4 rule below. The gate is the full contiguous
    # 7-col header run, which the 8-col (Stk.Value — saraswati_lstsl, caught
    # earlier anyway) and 9-col (extra Issue) Micropro siblings both break.
    if ("lstslopenrecd.salescloseorderpend" in low.replace(" ", "")
            and "stk.value" not in low):
        return "stock_lstsl"
    if "stock & sales" in low:
        if "- prev* max*" in low:
            return "technomax_stock"
        return "simple4"
    if (
        "open" in low
        and ("in" in low or "purchase" in low)
        and ("out" in low or "sale" in low)
        and "close" in low
    ):
        return "simple4"

    if re.search(r"s\.?no\s+product\s+name\s+packing\s+opening\s+purchas", low):
        return "siva_stock"

    return "generic"

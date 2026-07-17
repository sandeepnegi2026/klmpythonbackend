import re


def detect_layout(text, n_rects):
    low = text[:3000].lower()
    # MediVision Platinum "Stock and Sales" report (SIND DISTRIBUTORS). Adobe-UTF-8
    # CID export: pdfminer can't map its glyphs, so pdf_io falls back to PyMuPDF and
    # the parser re-reads word x-coords via fitz (right-aligned numbers, blank cells).
    # "medivision" + "stock and sales" + "companies:" is unique — cannot steal any
    # other vendor; MUST precede the coarse "stock and sales" -> simple4 rules below.
    # RAJU PHARMA MediVision "Stock and Sales" — WIDER Add/Less adjustment grid. Shares
    # "medivision"+"stock and sales"+"companies:" with the SIND sibling below, so it MUST
    # precede that rule; the "Add qty Less qty Add val Less val" run is absent from SIND.
    if "salesavaladdqtylessqtyaddvallessvalclqtyclval" in low.replace(" ", ""):
        return "medivision_stock_sales_addless"
    if "medivision" in low and "stock and sales" in low and "companies:" in low:
        return "medivision_stock_sales"
    # --- 15July KLM stock_pdf layouts. Each currently mis-routes (to generic /
    #     simple4 / prompt / marg_opstk) and lands RED; each gate keys on a compact
    #     header run UNIQUE to its export (verified — the full regression holds), so
    #     it reclaims only its own files. Placed high so the coarse fallbacks below
    #     cannot grab them first. ---
    _c15 = low.replace(" ", "")
    # JAGNATH per-division MediVision "Stock and Sales" — singular "Company:" band
    # (+Purc & prev-month sale cols). The SIND "Companies:" whole-report sibling above
    # returns first, so this only catches the per-division dialect. Positional (PyMuPDF x1).
    if ("medivision" in low and "stock and sales" in low and "company:" in low
            and "companies:" not in low):
        return "medivision_company_stock_sales"
    # HEMA SUNDHAR: Code/LM-SALE/Receipts/AGE dialect — the "…Closing Closing AGE"
    # terminus is disjoint from the batch-wise "…Closing Closing Value" sibling.
    if "openingreceiptstotalsalesclosingclosingage" in _c15:
        return "klm_lmsale_receipts_age"
    # THANE xtraRepStockAndSales: Op Bal|Purc|Sale|Sal Val|In/Out|Stk|Stk Val|3M
    # (signed In/Out stock adjustment). Positional (PyMuPDF).
    if "purcsalesalval" in _c15 and "in/out" in low:
        return "klm_stock_sales_inout_expiry"
    # METRO MEDICAL AGENCIES_: Product Name|Unit|Pack desc|Op|Purc|Sale|Cl qty — 4 qty
    # cols, NO value column.
    if "unitpackdescoppurcsalecl" in _c15:
        return "stock_unit_op_purc_sale_cl"
    # AGARWAL: Op.Bal.|Receipt|Total|Issue|Expiry|Closing|Near (Expiry=outflow, Near
    # dropped). The "…Total Issue Expiry Closing Near" run appears in no other layout.
    if "totalissueexpiryclosingnear" in _c15:
        return "stock_opbal_issue_expiry_near"
    # AAGAM pharmabyte single-page "Stock and Sale Statement" — doubled scheme run
    # P.Val/P.Sch/S.Qty/S.Sch/S.Val WITH a StkAd column and NO CrQty. The StkAd gate is
    # required: the StkAd-LESS pharmabyte siblings (VISNAGAR-COSMO/AAGAM-SSS/... ) already
    # parse on marg_opstk_statement below and MUST stay there, and this parser mis-reads a
    # StkAd-less body — so only the StkAd-bearing export is reclaimed. Overrides marg_opstk.
    if ("p.valp.schs.qtys.schs.val" in _c15 and "stkad" in _c15
            and "crqty" not in _c15):
        return "stock_sale_stmt_stkad"
    # NOTE: two builder layouts for this batch are intentionally NOT gated here.
    #  * stock_item_desc_oric_movement (AMETOMBI): its header (ITEM DESCRIPTION OPENING
    #    RECEIPT ISSUE CLOSING M.EXP) is byte-identical to ~38 simple4/stock_oric_pairs
    #    baselines (ANIL, KRISHNA CARE, VINEET, MARUTI, …), so no header token can
    #    separate them and this parser mis-reads those files. AMETOMBI stays on simple4.
    #  * prompt_datewise_amount_cols (OMKAR/PATEL/SHAH): its sub-header run
    #    ('qtyqtyqtyamountqtyamount' / '…freeinstqtyamount') is byte-identical to the base
    #    `prompt` baselines (OMKAR-PEDIA, ALL CARE, ANJALI, …) which `prompt` parses
    #    correctly. These files stay on the base `prompt` layout.
    # ===== 15 July RED-cluster Class-B overrides (batch 2) =====================
    # Each file currently mis-routes to a coarse fallback below (simple4 / generic /
    # stock_qoh / marg_stock_long / qty_value_total / prompt / toreo / marg_opstk) and
    # lands RED. Every gate keys on a compact header run (spaces-stripped `_c15`,
    # first 3000 chars) UNIQUE to its export, so it reclaims only its own files; the
    # full regression + 15July sentinels hold. Ordered so superset tokens win first.
    # SmartPharma360 reps 13-col (superset of the tstock variant below — MUST precede it).
    if "o.stkt.stockpurcpurc.retreplace.s.qtys.free" in _c15:
        return "smartpharma_reps_ostk_replace"
    if "o.stkt.stockpurcpurc.retreplace." in _c15:
        return "klm_smartpharma_stocksale_tstock"
    # PHARMA ASIA (SimpleFormat) — requires the "(simpleformat)" banner; MUST precede the
    # coded dualvalue sibling whose 'closingsalesvaluestockvalue' token is a substring here.
    if ("openingreceiptsalesclosingsalesvaluestockvalue" in _c15
            and "(simpleformat)" in _c15):
        return "r15_pharma_asia_simpleformat"
    # PHARMA ASIA KLM (DERMA) coded dualvalue — SAME export as SimpleFormat above, but
    # its text layer x-interleaves the Description/Packing runs, so the '(simpleformat)'
    # banner never appears compactly ('Stock StatemPreinntt D(Saimtep...') and the gate
    # above cannot fire; the column-header run survives intact. The parser rebuilds names
    # from content-stream char runs (they are clean in stream order — NOT scrambled).
    # 'pharma asia distributor' + NOT-'(simpleformat)' keeps the clean-text sibling
    # (KLM.pdf) on r15_pharma_asia_simpleformat and steals nothing else (corpus-probed).
    if ("openingreceiptsalesclosingsalesvaluestockvalue" in _c15
            and "pharma asia distributor" in low
            and "(simpleformat)" not in _c15):
        return "r15_klm_pharmaasia_code_open_recv_sales_close_dualvalue"
    # HMRS PCode positional (OPSTK PURC PSCH IN SALE SSCH OUT STOCK).
    if "opstkpurcpschinsalesschoutstock" in _c15:
        return "klm_pcode_opstk_psch_ssch_positional"
    # NU SRI SHYAM Marg "Sales And Stock (Detail)" tri-page (OpStock OpValue PurchaseQty).
    if "opstockopvaluepurchaseqty" in _c15:
        return "nu_srishyam_sales_stock_detail"
    # SUDHA ENTERPRISES page-split (doubled RECEIVE header + bare right-page header).
    if ("openingopeningreceivereceiveissue" in _c15
            and "issueclosingclosingexpiry" in _c15):
        return "sudha_open_recv_issue_close_split"
    # AKSHAR 7-col (garbled 'Purchase FreTeotal' run).
    if "purchasepurchasefreteotalsales" in _c15:
        return "akshar_open_pur_free_total_sale_free_close"
    # KLM Qoh paired qty+value (ABHIRAM) — require the 'qoh' terminus so the SRI BABA
    # smartpharma sibling (same 'purc.tot purc value sales' run but a Closing/returns
    # terminus and NO Qoh column) is left on its own baseline.
    if "purc.totpurcvaluesales" in _c15 and "qoh" in low:
        return "stock_qoh_paired_value"
    # KLM Sales & Stock Qty+Value dual Free-Q (two Free-Q cells in Receipt AND Issue).
    if "freeqreceipt/purtotalissuefreeqissue/sales" in _c15:
        return "klm_ss_qty_value_dualfree"
    # GAYATRI Monthly S&S (Inward/Other/Closing — 'purchase' leaks from the footer).
    if "packingopeninginwardsalesotherclosing" in _c15:
        return "r15_monthly_ss_inward_other_closing"
    # LAXMI KLM LAB 5-col positional (Opening Receipt Sales Closing StockValue).
    if "openingreceiptsalesclosingstockvalue" in _c15:
        return "r15_klm_lab_open_recv_sales_close_value_positional"
    # NAIK 'STOCK & SALES REGISTER' 17-col positional (back-to-back Receipt/Receipt Free).
    if "receiptreceiptfreetotalsaleinst.freegoodssaleg.r.close" in _c15.replace("\n", ""):
        return "r15_klm_ss_register_receipt_inst_gr_positional"
    # NAVKAR two-page split ('Prev.Last Prev.Sal Opening Purchase P.Free' page-0 header).
    if "prev.lastprev.salopeningpurchasep.free" in _c15:
        return "r15_klm_ss_prevlast_twopage_positional"
    # JAY AMBE Monthly S&S short (Goods Ret. + Total, no Order cols).
    if ("openingpurchasegoodsret.totalsalepurc.ret.balance" in _c15
            and "monthly stock & sales statement" in low):
        return "r15_jayambe_monthly_ss_balance"
    # M.M.TRADERS 'Stock and Sales Report (Month)' — 31-col full-word (SaleQuantity/ILast).
    if ("stockandsalesreport(month)" in _c15 and "packopeningstock" in _c15
            and "salequantity" in _c15 and "ilastsalesqty" in _c15):
        return "klm_ss_month_totalstock_ilast_positional"
    # SAMBARI 'Stock sales statement(Combined)' FLAT pipe render — discriminated from the
    # VISION wrapped-grid sibling (same header) by many clean 10+-pipe DATA lines (full text).
    if ("statement(combined)" in _c15 and "stocksalesstatement" in _c15
            and "totalclosing" in _c15 and "closingvalue" in _c15 and "totalsale" in _c15
            and sum(1 for _l in text.splitlines() if _l.count("|") >= 10) >= 5):
        return "klm_ss_combined_pipe_flat"
    # METRO Sales & Stock Statement — trailing single-letter 'C' value column
    # ("...Sales Cl Bal C"). Exclude the METRO "Divisionwise" sibling whose header is
    # "...Sales Cl Bal CP" (compact 'salesclbalcp'): that variant parses cleanly on
    # stock_op_pur_total_sale_close, whereas this glyph parser mis-reconciles it.
    if "salesclbalc" in _c15 and "salesclbalcp" not in _c15:
        return "metro_sales_stock_statement_glyph"
    # BHAGYODAY KLM 'Stock and Sales report' sparse Mar/Apr movement block — shares Venus's
    # column header, separated by the Mar/Apr prev-month pair and the absence of 'dec'.
    if ("cr.db.adj.cstkcval" in _c15 and "maraprop." in _c15 and "dec" not in low):
        return "klm_ss_marapr_positional"
    # VENUS PHARMA (Ahmedabad) KLM 'Stock and Sales report' — Apr/May prev-month pair
    # variant of the sparse positional movement block above (Op/Pur/SP/Sale/SS/Cr/Db/Adj/
    # C Stk/C Val). Shares venus_stock_statement's column header but its Apr/May pair +
    # absence of 'dec' separates it from the 7 Dec/Jan venus_stock_statement baselines and
    # from the Mar/Apr BHAGYODAY sibling above; corpus-probed to steal nothing else.
    if ("cr.db.adj.cstkcval" in _c15 and "aprmayop." in _c15 and "dec" not in low):
        return "venus_ss_aprmay_positional"
    # NOTE: prompt_datewise_pack_free_inst (SHAH 'klm all') is intentionally NOT gated:
    # its sub-header run "free inst qty amount a3mn" is shared by ordinary KLM Prompt
    # datewise files (e.g. 'klm div.pdf') that the base `prompt` parser handles fine, and
    # this variant parser turns those AMBER files RED. Only SHAH's bare-number-Pack body
    # actually needs it, and that is not separable by a header token — so SHAH stays on
    # base `prompt` (RED), like the batch-1 prompt_datewise_amount_cols revert.
    # NOTE: marg_item_opstk_pval_psch_sval (VISNAGAR MF070) is intentionally NOT gated:
    # its positional parser GLYPH-INTERLEAVES the item code into the product name
    # ("MKVFELS0MK91R.." for "EKRAN"), on both the target AND the VISNAGAR/AAGAM
    # marg_opstk_statement baselines it would reclaim, so despite a higher reconcile it
    # is a name-quality REGRESSION. Those files stay on marg_opstk_statement (clean names).
    # MEDICA Ultimate Stock Statement — APR/MAR trailing-month run (toreo has FEB/JAN).
    if "stkvalaprmar" in _c15:
        return "medica_stock_apr_mar"
    if "liquidation" in low and "sh.exp" in low:
        return "dolphin_stock"
    if "opstk" in low and "purch" in low and "in/ot" in low:
        return "toreo_stock"
    # SAI KRISHNA (KLM ERP) 'STOCK AND SALES ANALYSIS' 9-col movement statement:
    # OPENING PURCHASE S.RETURN OTHERS(in) SUB TOTAL SALE P.RETURN OTHERS(out) CLOSING
    # (every zero cell prints '-'). Coarse simple4/stock_simple_7col drop the outflow
    # columns -> false SANITY_FAILED. The compact run 'subtotalsalep.returnothersclosing'
    # (mid-table SUB TOTAL + doubled OTHERS + S.RETURN) is in NO other gate. MUST precede
    # every coarse rule below.
    if "subtotalsalep.returnothersclosing" in low.replace(" ", ""):
        return "stock_ss_analysis_sret_others"
    # MEYON DRUGS 'Stock Statement for the month of ...' — per-division KLM
    # export with a wrapped 3-line header (Prev.month Sales / Items Packing Rate
    # Op_Stk Rcpts P.Ret Sales Hos.Sal Brk Repl Cl_Stk Value / APR MAY). Most of
    # the 8 movement cells are blank per row so the flat text collapses and the
    # generic fallback mis-binds; a positional x-bucket parser is needed. The
    # underscore tokens 'op_stk'/'cl_stk' appear in NO other stock_pdf gate; the
    # combination op_stk+rcpts+hos.sal+cl_stk is unique to this vendor (kluster's
    # 'hos.sales'+'lms' rule below cannot fire — this header has no LMS column).
    if "op_stk" in low and "rcpts" in low and "hos.sal" in low and "cl_stk" in low:
        return "meyon_prevmonth_stock"
    if "hos.sales" in low and "lms" in low:
        return "kluster_stock"
    # PharmAssist (C-Square) 'Stock and Sales Mfac Group Wise Report' — glyph-interleaved
    # text needs positional (x-coordinate) parsing. Title token is unique to this export.
    if "mfac group wise" in low:
        return "pharmassist_mfac"
    # C-Square 'Manufacturerwise Stock and Sales Report' (UNIVERSAL DRUG LINES, TIRUR):
    # Item|Pack|L.Sale|SaleRate|Op.Qty|Pur.Qty|Sal.Qty|Sal.Val|Cr.Qty|Adj|Bal.Qty|Bal.Val,
    # banded by 'Manufacture: KLM LABORATORIES <DIV> DIV.'. The leading Item/Pack/L.Sale/
    # SaleRate glyph-interleave in the text layer, so a trailing-8-numeric anchor is used.
    # The compact title 'manufacturerwisestockandsalesreport' + the exact header run
    # 'op.qtypur.qtysal.qtysal.valcr.qtyadjbal.qtybal.val' is unique to this C-Square export
    # (no other stock_pdf gate references 'manufacturerwise' or this Op/Pur/Sal.Val/Bal.Val
    # header run), so it cannot steal other vendors. MUST precede the generic fallthrough.
    _c_mfrw = low.replace(" ", "")
    if ("manufacturerwisestockandsalesreport" in _c_mfrw
            and "op.qtypur.qtysal.qtysal.valcr.qtyadjbal.qtybal.val" in _c_mfrw):
        return "csquare_manufacturerwise_stock_sales"
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
    # SmartPharma360 'Stock And Sales Report' (SRI BABA MEDICAL DISTRIBUTORS, KLM):
    # header Product Name|Pack|Open stock|Opening Value|Pur.Total|Pur.Value|Sales Total|
    # Sale Value|sale ret total|sale ret val.|Closing qty|Closing Value|Age (10 movement/value
    # cols + Age, 11 numeric tokens/row, all printed). The coarse 'generic' fallback mis-binds
    # the interleaved value columns into qty fields. Gate on the unique header run
    # 'openstockopeningvaluepur.totalpur.value' + 'saleretval' (also the smartpharma360
    # watermark) — absent from every other stock layout; the BlueFox central_stock_sales export
    # below is additionally gated on 'br/e', absent here. MUST precede that rule.
    if ("openstockopeningvaluepur.totalpur.value" in low.replace(" ", "")
            and "saleretval" in low.replace(" ", "")):
        return "smartpharma_sas"
    _c_central = low.replace(" ", "")
    if (
        ("stockandsalesreport" in _c_central or "stockandsalesfrom" in _c_central)
        and "br/e" in _c_central
        and "salevaluef.valueqtybal.val" in _c_central
    ):
        return "central_stock_sales"
    # MEDICHEM PHARMA (Haridwar, KLM ERP) "Stock and Sales Statement from <d> to <d>"
    # — one file per KLM division. Sales columns are printed BEFORE purchase columns and
    # every zero cell prints an explicit '-', giving a fixed 14-numeric-token tail per row
    # (Opening | Sales Qty/Free/Amount/Return | Purchase Qty/Free/Amount/Return | Other |
    # Closing Bal/Amount | Expiry In/Out). Generic mis-binds these (Sales->purchase, closing
    # lands on the always-dash Expiry-Out). The header run "Other Closing Closing Expiry
    # Expiry" (compact 'otherclosingclosingexpiryexpiry') is unique to this export and
    # appears in no other stock layout. MUST precede the coarse simple4/generic fallthroughs.
    _comp_mch = low.replace(" ", "")
    if "stockandsalesstatement" in _comp_mch and "otherclosingclosingexpiryexpiry" in _comp_mch:
        return "medichem_ss_expiry"
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
    # RAOUSHAN PHARMA SwilERP "Sales & Stock Statement Company [Summary]": a
    # division-summary dialect with a leading item CODE and the header run
    # NO | PRODUCT/COMPANY | OP QTY | IN QTY | OP+IN QTY | OUT QTY | OUT AMT | CL QTY |
    # CL AMT. Its title carries the substring "stock statement" and the header has
    # "product", so without this gate it falls through to the coarse "stock statement"
    # + "product" -> simple4 rule, which mis-maps the 7-number tail (OP+IN cross-check
    # -> a movement col) -> ~54% false SANITY_FAILED. The token "op+in" is unique to
    # this export (no other stock layout prints an OP+IN column), so it cannot steal any
    # sibling. Reconcile is closing = OP + IN - OUT.
    if "sales & stock statement" in low and "op+in" in low:
        return "swil_stock_company_summary"
    # Marg "Sales & Stock Statement" (banner "Page No.1 Sales & Stock Statement
    # (From .. Upto ..)"), division-banded (KLM <DIV>). Two variants of ONE family:
    #   NARROW (KAMLAWATI): 11 qty/value cols — Op q/v | Receipt q/v | Total | Issue
    #     q/v | Closing q/v | NearExpiry | MSR. Compact tail 'closingclosingbalanearmsr'
    #     is unique to the narrow export.
    #   WIDE (KALYANI): 15 cols — adds ReturnToCOM (purchase_return) + RetFromCustomer
    #     (sales_return) + Expiry/Breakage (exp_damage); gated on 'retreturntocom' +
    #     'retfromcustomerexpiryexpiryclosing' (both absent from the narrow export).
    # Both currently mis-route to the coarse qty_value_total / stock_simple_7col rules
    # below, which drop Value into Qty fields -> 100% false SANITY_FAILED. Gate tokens are
    # corpus-unique (0/1040 Data PDFs); MUST precede qty_value_total/simple4/stock_simple_7col.
    _c_mss = low.replace(" ", "")
    if "sales & stock statement" in low and (
        "closingclosingbalanearmsr" in _c_mss
        or ("retreturntocom" in _c_mss and "retfromcustomerexpiryexpiryclosing" in _c_mss)
    ):
        return "marg_sales_stock_statement"
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
    # KLM 'Stock And Sale Report(Month)' — Rcpt dialect (SHREE SHIVASAKTHI
    # MEDICAL). Sibling of klm_stock_sales_month / klm_stock_sales_month_repq;
    # header 'Product Name Pack OpStk Rcpt Apr2 May2 sales Cl.S StkValu SalValu
    # Expiry Age' (title says 'Sale' not 'Sales', has no PrvSa/RepQ tokens).
    # Zero cells blank out + right-aligned => positional x-bucket parser. Gate
    # on the compact header run 'opstkrcpt' + 'cl.sstkvalusalvalu' (unique to
    # this export; the two prev-month cols Apr2/May2 rename monthly so they are
    # NOT gated). Must precede the prvsa rule below and the generic fallthrough.
    _comp_rcpt = low.replace(" ", "")
    if ("stockandsalereport(month)" in _comp_rcpt and "opstkrcpt" in _comp_rcpt
            and "cl.sstkvalusalvalu" in _comp_rcpt):
        return "klm_stock_sales_month_rcpt"
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
    # KLM 'Stock And Sales Report(Month)' — TotS/Sale_Val dialect (VASAN MEDICAL
    # AGENCIES; one report per division). Header: 'ProductName Pack Op.Qt Purch Free
    # AprP_ MayL_ C_Sal Free Repl Adj Tot.S Sale_Val' (two prev-month cols AprP_/MayL_
    # rename monthly, NOT gated). Zero cells blank out + right-aligned => positional
    # x-bucket parser. Gate on 'op.qtpurchfree' + 'tot.ssale_val' + title; disjoint from
    # the sibling KLM-month dialects (opstpursalefreeadjcl.s / opstpurq / openingpureilast
    # / opstkrcpt). MUST precede those siblings and the coarse fallbacks below.
    _comp_tots = low.replace(" ", "")
    if ("stockandsalesreport(month)" in _comp_tots and "op.qtpurchfree" in _comp_tots
            and "tot.ssale_val" in _comp_tots):
        return "klm_stock_sales_month_tots"
    _comp_repq = low.replace(" ", "")
    if ("stockandsalesreport(month)" in _comp_repq and "opstpurq" in _comp_repq
            and "repqsalevalue" in _comp_repq and "stockvaluelpd" in _comp_repq):
        return "klm_stock_sales_month_repq"
    compact = low.replace(" ", "")
    # KLM 'Stock And Sales Report(Month)' — NetStock dialect (BIOLEND): header
    # 'Opening Pure ILast Sale Free Rpl Total NetStock Val SaleNet@Pur'. Positional
    # x-bucket parser (blank zero cells). Tokens 'openingpureilast'/'netstock'/'@pur'
    # appear in no other gate and are disjoint from the repq/opstpursalefreeadjcl.s
    # siblings; MUST precede the n_rects>400 -> marg_bordered rule (each page has 443
    # rects) and the klm_stock_sales_month sibling below.
    if ("stockandsalesreport(month)" in compact and "openingpureilast" in compact
            and "netstock" in compact and "@pur" in compact):
        return "klm_stock_sales_month_netstock"
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
    # NEW SUJITH PHARMA ships the SINGLE-PAGE PharmAssist export with a bare "Br" column
    # (no Bsc), so 'brbsc' is absent; but the wide right-block header (BVal/SVal/Order/Adj)
    # is present and unique to this single-page family. Accept it as an alternative to
    # 'brbsc'. 'item code'/'item name' ABSENT keeps it off the page-split sibling below.
    if (
        "stock and sale report" in low
        and "pharmassist" in low
        and (
            "brbsc" in low.replace(" ", "")
            or (
                "bval" in low.replace(" ", "")
                and "sval" in low.replace(" ", "")
                and "order" in low.replace(" ", "")
                and "adj" in low.replace(" ", "")
                and "item code" not in low
            )
        )
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
    # KLM "Stock Sales Statement (Small)" wrapped positional export (MUDRAA/WARAD):
    # Rate|Openin|Reciept|Sales|Free|SalesRt|Closing (note the vendor's misspellings
    # 'Reciept'/'SalesRt'). Numbers wrap their low-order digits onto continuation lines,
    # so a positional x-bucket parser is required. The compact title 'stocksalesstatement
    # small' + the misspelled 'reciept'+'salesrt' tokens are unique to this KLM export
    # (mutually exclusive with combined_pdf's 'statement(combined)'), so it steals nothing.
    if (
        "stocksalesstatementsmall" in _compact
        and "reciept" in _compact
        and "salesrt" in _compact
    ):
        return "klm_stock_sales_small_pdf"
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
    # PADMAJA is the 9-column sibling: header 'O.Bal Purches Sal.Ret Total Sales Pur.Ret
    # Cl.Bal Cl.Value Age' (ONE Total, and dotted Sal.Ret/Cl.Bal spellings), so accept the
    # 'sal.ret'/'cl.bal' variants alongside SRI DURGA's 's.ret'/'clbal'.
    _compact = low.replace(" ", "")
    if "stock&salesstatementdetailed" in _compact or (
        "o.bal" in _compact
        and "purc" in _compact
        and ("s.ret" in _compact or "sal.ret" in _compact)
        and ("clbal" in _compact or "cl.bal" in _compact)
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
        # Prompt ERP 'Stock Statement (Datewise)' geometry-A DOUBLE-AMOUNT printed on a
        # ruled/bordered page (PATEL MEDICAL AGENCIES/KLM1). The bordered grid parser
        # mangles these rows (splits 'EN'/'T' out of product names, dumps op/pur/sales
        # into raw_* junk -> SANITY_FAILED), while parse_prompt_datewise_amount_cols
        # reconciles 222/223 on the text. Exposure is CLOSED to files that already
        # detect prompt_bordered here: corpus (RAMESH KLM MAY) and baselines (GANESH
        # COSMO/COSMOCOR/COSMOQ/DERMA/DERMACOR/PEDIA, SHREE GURU MEDIBILL) all lack the
        # geometry-A sub-header run, so they keep prompt_bordered.
        if "qtyqtyqtyamountqtyamount" in _c15 and "a3mne/eageexp" in _c15:
            return "prompt_datewise_amount_cols"
        # Prompt ERP stock with a Manufacturer-Name column + Opening/Purchase/Sale/
        # Closing/Rate/Stock-value layout (RAMESH). The bordered parser mis-columns it
        # (value-in-qty slots -> SANITY_PARTIAL); the dedicated parser maps mfr + value.
        # Both header tokens are unique to this Prompt variant, absent from the plain
        # prompt_bordered exports, so this cannot steal them.
        if "openingpurchasesaleclosingratestock" in _c15 and "manufacturername" in _c15:
            return "prompt_stock_mfr_value"
        return "prompt_bordered"
    # PURANI HOSPITAL SUPPLIES "MFR Stock and Sales Report" — HTML-print-to-PDF twin of
    # the stock_xlsx purani_mfr_stock_sales layout (one PDF per KLM division). Every cell
    # is boxed (>400 rects) so the n_rects>400 -> marg_bordered catch-all below steals it
    # and mis-binds -> SANITY_FAILED. The 18-col table right-aligns every number and wraps
    # each product name over several lines, so a positional (word x1) parser is required.
    # The compact header run 'o.stpurfreeprtnmbmonlmonmonc.st' is unique to this Purani
    # export; paired with the 'mfr stock and sales report' title it cannot steal any other
    # vendor. MUST precede the n_rects>400 rule below.
    if ("mfr stock and sales report" in low
            and "o.stpurfreeprtnmbmonlmonmonc.st" in low.replace(" ", "")):
        return "purani_mfr_stock_sales_pdf"
    # KAKADE AGENCIES "Stock and Sales Statement" (Marg/MVGold browser-print export;
    # timestamp masthead "6/29/26, 5:49 PM Stock and Sales Statement"). 14 trailing
    # numeric cols: Opst|Purc|S.R.|Sale q/v|P.R.|Exp+Non-Mov purc/sale|Closing q/v|Near.Exp.
    # Every cell is boxed (>400 rects) so the marg_bordered catch-all below steals it and
    # mis-reads sale/closing -> SANITY_FAILED. Positional 14-count parser (needs file_bytes).
    # The compact run 'opstpurcs.r.' + 'near.exp' under the 'stockandsalesstatement' title
    # is corpus-unique (0/1040 Data PDFs); MUST precede the n_rects>400 -> marg_bordered rule.
    _comp_kak = low.replace(" ", "")
    if ("stockandsalesstatement" in _comp_kak and "opstpurcs.r." in _comp_kak
            and "near.exp" in _comp_kak):
        return "marg_stock_sales_expiry_positional"
    # SUN TRADERS "Stock N Sales Status" (Op/In/Out/Cl qty grid, Data Spec header) — a
    # ruled export that the coarse n_rects>400 catch-all would misroute to marg_bordered
    # and mis-parse. Keyed on 3 tokens unique to this export (probed: matches only the
    # SUN TRADERS files across the corpus). MUST precede the marg_bordered catch-all.
    if ("stock n sales status" in low and "opqtyinqtyoutqtyclqty" in low.replace(" ", "")
            and "data spec" in low):
        return "suntraders_stock_n_sales_status"
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
    # SHANTI MEDICOS SwilERP 'Sales & Stock Statement' — capital_stock_sale_stmt family
    # (Op.Bal/Receipt/Total/Issue/Closing) with TWO extra interior columns Free Q + Expiry
    # Breakage inserted between Issue and Closing (7 qty numbers/row). Base simple4 pops only
    # the first 4 -> Total->sales_qty, Issue->closing -> false SANITY_FAILED. The compact run
    # 'op.bal.receipttotalissuefreeqexpiryclosing' is corpus-unique (capital lacks 'freeqexpiry').
    if "op.bal.receipttotalissuefreeqexpiryclosing" in low.replace(" ", ""):
        return "stock_opbal_free_expiry"
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
    # KLM LABS (DERMA) 'STOCK & SALES STATEMENT' two-page receive/close statement (SHREE
    # DURGESHWARI). PAGE 1 = OPENING/PURCHASE/SALE RETURN/REPLACE+/TOTAL RECEIVE; PAGE 2 (no
    # names) = SALE/P/R/REPLACE+/CLOSING/RATE. The receipts-only marg_pds_replace sibling below
    # shares the page-1 'replace+' header and would steal it. The page-2 header run
    # 'salep/rreplace+closing' is unique to this two-page statement. Scan the FULL text (not the
    # 3000-char `low`) so a long page 1 cannot push page-2 header out of the window. MUST precede.
    if "salep/rreplace+closing" in text.lower().replace(" ", ""):
        return "klm_ss_statement_receive_close"
    # marg sub-families: must beat the coarse marg_stock_long rule below
    if "replace+" in low or ("product description" in low and "opening" in low and "replace" in low):
        return "marg_pds_replace"
    if "opening purchase free sale free closing" in low:
        return "marg_open_pur_free_sale"
    if "stock & sales analysis" in low and "purchasesreturnothers" in low.replace(" ", ""):
        return "marg_movement_detail"
    # KLM 'STOCK & SALES ANALYSIS (KLM <DIV>)' per-company export with a
    # "Reorder : Sale X .." option (VANDANA MEDICAL AGENCIES). SAME 14-col
    # S/R P/R SAMPLE M.EXP structure as marg_stock_analysis_full (SIDDHIVINAYAK)
    # below, but this vendor prints WHOLE-unit free goods and shows PURCHASE and
    # FREE as separate columns, so folding them (17+3 -> 20) reads wrong to the
    # user. The dedicated layout breaks purchase_free/sales_free out into their own
    # canonical fields. Distinguished from SIDDHIVINAYAK by BOTH the company-in-
    # parens title run "stock & sales analysis (klm" AND the "reorder :" option
    # token — SIDDHIVINAYAK's title ("STOCK & SALES ANALYSIS 01-05-2026 - ...")
    # carries NEITHER, so it stays on marg_stock_analysis_full (its half-unit free
    # goods require the fold). MUST precede the marg_stock_analysis_full gates below.
    if (
        "stock & sales analysis (klm" in low
        and "reorder :" in low
        and "s/r" in low
        and "p/r" in low
        and "sample" in low
        and "m.exp" in low
    ):
        return "klm_stock_sales_analysis_free"
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
    # SRI SHIRIDI SAI "STOCK AND SALES STATEMENT" free-goods variant: Item Name | Pack |
    # Opening | Received | Free | Issued | Free | Closing | Free (7 qty numbers/row). It
    # carries 'Opening Value'/'Sales Value On prate' summary tokens that spuriously trip the
    # loose value_pairs rule below (rate+opening+issue+value), whose >=8-number parser then
    # yields 0 rows -> generic mis-bind. The existing marg_open_pur_free_sale parser binds
    # all 7 columns correctly (Received->purchase, Issued->sales); gate on the unique
    # 'received free'+'issued free' run and route here BEFORE value_pairs.
    if "item name" in low and "received free" in low and "issued free" in low:
        return "marg_open_pur_free_sale"
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
    # SREE SUPREME / ANANDH DOSPrinter "STOCK & SALES STATEMENT" — grouped two-row
    # header OPENING/RECEIPT/SALES(LAST,QTY,FREE)/ADJMT/CLOSING(QTY,FREE,VALUE)/AGE.
    # Every zero cell prints '-' so token counts vary -> needs a positional parser.
    # The doubled sub-header run is unique to this export; MUST precede stock_simple_7col
    # (which otherwise maps closing_stock <- SALES-LAST and fails sanity).
    if "qtyqtyfreelastqtyfreestockqtyfreevaluedays" in re.sub(r"\s+", "", low):
        return "stock_sales_statement_adjmt_positional"
    # Marg "STOCK AND SALES ANALYSIS" — AVA/Apr/OP.BAL/.../B.Sale/SALE/BAL + BVAL/SVAL
    # column variant (MALU MEDICO PVT LTD, Sangli; KLM division-banded). Header:
    #   ITEM NAME PACK AVA Apr OP.BAL PUR. PR. ADJ. SR. B.Sale SALE BAL BVAL SVAL N.MOV REMARKS
    # Every zero cell prints '-' and numbers are right-aligned, so the flat text
    # collapses -> the coarse stock_simple_7col rule below (name/pack/open/purchase/
    # closing all present) mis-binds sales/closing onto the always-'-' cells
    # (sales_qty=0, closing~0, 0% sanity). Needs a POSITIONAL x-bucket parser.
    # This is a distinct column family from the ampersand-titled marg_stock_analysis_*
    # variants (S/R P/R SAMPLE M.EXP) — this one uses the word "AND" and a B.Sale/
    # SALE/BAL/BVAL/SVAL tail. Gate on 'stockandsalesanalysis' + the compact header run
    # 'b.salesalebalbvalsval' (+ 'avaaprop.bal'); this token set is corpus-unique
    # (0/1040 Data PDFs) and appears in no other stock layout, so it cannot steal any
    # other vendor. MUST precede the coarse stock_simple_7col rule below.
    _comp_ava = low.replace(" ", "")
    if (
        "stockandsalesanalysis" in _comp_ava
        and "b.salesalebalbvalsval" in _comp_ava
        and "avaaprop.bal" in _comp_ava
    ):
        return "marg_stock_ava_bval_sval"
    # A.K. MEDICAL / SRI LAKSHMI ANNAPURNA "STOCK AND SALES STATEMENT" (KLM ERP) — two
    # header-driven variants currently mis-detected as the coarse stock_simple_7col below.
    # AGE variant header ends 'Opening Received Issued Closing AGE'; VALUE variant is
    # 'Opening Received Issued Value Closing SReturn PReturn free'. Gate on the title plus
    # each variant's exact compact header run; the bare KRISHNA stock_received_issued header
    # ('...Received Issued Closing') has NEITHER token so it is not stolen. MUST precede the
    # coarse stock_simple_7col rule.
    _c_klmri = low.replace(" ", "")
    if "stockandsalesstatement" in _c_klmri and (
        ("openingreceivedissued" in _c_klmri and "closingage" in _c_klmri)
        or "valueclosingsreturnpreturnfree" in _c_klmri
    ):
        return "klm_received_issued"
    # SRI SUBRAHMANYA PHARMACEUTICALS 'STOCK AND SALES STATEMENT': division-banded
    # KLM report with header 'Item Name Pack Opening Received Issued Closing stock
    # Closing'. Interior cells (Received/Issued) blank out for no-movement rows, so the
    # printed token count varies (2-5 numbers) and the flat stock_simple_7col parser
    # (which this file otherwise reaches: its top value-summary carries 'Purchase') keeps
    # only the ~8 rows that print all five numbers and drops every sparse row. Needs a
    # positional (x1-binned) parser. The compact header run 'receivedissuedclosingstock'
    # (Received + Issued + Closing stock, glued) is unique to this export — the sibling
    # klm_received_issued (Age variant, claimed just above) has no 'stock' column and the
    # stock_received_issued flat layout requires 'rplqty'. Reconcile closing = opening +
    # received - issued.
    if "receivedissuedclosingstock" in _c15:
        return "subrahmanya_stock_recd_issued"
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
    # AMRITA "STOCK & SALES ANALYSIS" — qty-only-Receipt variant (COSMOCOR division): the
    # RECEIPT group has a QTY column ONLY, giving 7 numeric cells/row (Opening q/v, Receipt q,
    # Issue q/v, Closing q/v). Its Issue+Closing tail satisfies the stock_oric_pairs gate below,
    # which then expects a paired Receipt value and shifts every column -> sanity 0.0. The full
    # sub-header run 'qty.valueqty.qty.valueqty.value' is NOT a substring of the paired run
    # 'qty.valueqty.valueqty.valueqty.value', so it can't steal the paired AMRITA files. MUST
    # precede stock_oric_pairs.
    if (
        "stock & sales analysis" in low
        and "qty.valueqty.qty.valueqty.value" in low.replace(" ", "")
    ):
        return "stock_oric_receipt_qtyonly"
    if (
        "opening" in low
        and "receipt" in low
        and "issue" in low
        and "closing" in low
        # whitespace-tolerant: D.D. ENTERPRISE keeps multi-space column gaps in the
        # "QTY.     VALUE     QTY.     VALUE" sub-header, so the single-spaced literal
        # misses it and it falls to the coarse simple4 rule (reads 8-num rows as 4).
        and (
            "qty. value qty. value" in low
            or "qty.valueqty.value" in low.replace(" ", "")
        )
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
        # SHAH 'Stock Statement (Datewise)' with a BARE-NUMBER Pack column ('klm all
        # 18-6-26'). Its column header is byte-identical to ordinary Prompt datewise
        # exports (ALL CARE 'klm div.pdf' AMBER corpus sibling; 'ALL CARE MEDICINES -
        # PROMP - SSS.pdf' GREEN baseline) which the base `prompt` parser handles fine
        # — a header-token-only gate was reverted once because it flipped the AMBER
        # sibling RED. Gate on the BODY instead, on all three of:
        #  (1) the 'Free Inst Qty Amount A3Mn' sub-header run (Prompt datewise family);
        #  (2) Order(s) tails 'N / N / N = N' (THREE-number runs — exactly what
        #      parse_prompt_datewise_pack_free_inst's strip regex expects) and ZERO
        #      two-number 'N / N = N' runs (klm div.pdf is all two-number: the r15
        #      parser cannot strip those and would emit 0 rows);
        #  (3) >=3 data rows whose numeric tail (after stripping the Order(s) run)
        #      holds >=9 numbers — the bare-number Pack leak that actually breaks the
        #      base `prompt` column mapping (SHAH: 16/39 rows; both ALL CARE files: 0,
        #      so all-text-Pack exports stay GREEN on the base `prompt` rule below).
        # MUST precede the base `prompt` rule.
        if ("opstk" in low and "a3mn" in low
                and "freeinstqtyamounta3mn" in low.replace(" ", "")):
            _ord3 = _ord2 = 0
            for _ln in text.splitlines():
                for _m in re.findall(
                        r"\d+(?:[ \t]*/[ \t]*\d+)+[ \t]*=[ \t]*-?\d+", _ln):
                    _k = _m.count("/")
                    if _k == 2:
                        _ord3 += 1
                    elif _k == 1:
                        _ord2 += 1
            if _ord3 >= 3 and _ord2 == 0:
                _strip3 = re.compile(
                    r"\s+\d+\s*/\s*\d+\s*/\s*\d+\s*=\s*-?\d+\s*$")
                _isnum = re.compile(r"^-?[\d,]*\.?\d+$")
                _wide = 0
                for _ln in text.splitlines():
                    _m = re.match(r"^\d+\s+(\D.*)$", _ln.strip())
                    if not _m:
                        continue
                    _toks = _strip3.sub("", _m.group(1).strip()).split()
                    _i = len(_toks)
                    while _i > 0 and _isnum.match(_toks[_i - 1].replace(",", "")):
                        _i -= 1
                    if len(_toks) - _i >= 9:
                        _wide += 1
                if _wide >= 3:
                    return "prompt_datewise_pack_free_inst"
        if "opstk" in low and "pur" in low and "a3mn" in low:
            return "prompt"
        if "stock statement for company" in low and "pks data" in low:
            return "pks_data"
        # SwilERP 'Sales & Stock Statement' 9-column Receipt/Issue/Retrn dialect (JAY
        # SHREE): Op.Bal|Receipt|Retrn|Total|Issue|Retrn|Closing|Dump|Near. Its header
        # says 'Op.Bal.' (not 'opening'), so it reaches this coarse rule which would pop
        # only the first 4 of the 9 numbers. The doubled Retrn + Total run is shared with
        # the 7-column sibling of this SwilERP family (PRAKASH MED. AGENCY: same header
        # WITHOUT the trailing Dump/Near, which stays on simple4), so gate additionally on
        # 'dumpnear' — the two extra columns that make this the 9-number dialect our
        # parser reads.
        _swil = low.replace(" ", "")
        if "receiptretrntotalissueretrnclosing" in _swil and "dumpnear" in _swil:
            return "swil_recv_issue_stock"
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

    # KLM 'STOCK AND SALES ANALYSIS' — P.Code-led per-division statement (PRABHAT
    # AGENCY). Header: P.Code ITEM NAME PACK OP. Pur. SP P.Ret SALE SS S.Ret Adj.
    # Cls.Stk <M1> <M2>. Clean text, fixed 11-token stat tail (blanks print '-').
    # Trailing two columns are prev-month sales whose labels rename per period, so
    # drop them positionally. The 'p.code'+'cls.stk'+'s.ret'+'adj.' column vocabulary
    # under the 'stock and sales analysis' title (word AND, not ampersand) is unique to
    # this KLM export — both PRABHAT files currently fall to 'generic'. MUST precede it.
    # KLM 'STOCK AND SALES ANALYSIS' — division-banded movement statement, NO P.Code
    # (SANTOSH ENTERPRISES). Header OPENING PURCHASE FREE P.RETURN FREE SALE FREE S.RETURN
    # FREE OTHERS CLOSING (11 qty cols, '-'=0). Without this it falls to 'generic', which
    # maps sales_qty<-PURCHASE-FREE and DROPS SALE -> 100% false SANITY_FAILED. The compact
    # run 'openingpurchasefreep.returnfreesalefrees.returnfreeothersclosing' is unique to this
    # KLM export; mutually exclusive with the P.Code sibling below (needs 'p.code').
    if ("stock and sales analysis" in low
            and "openingpurchasefreep.returnfreesalefrees.returnfreeothersclosing"
            in low.replace(" ", "")):
        return "klm_stock_sales_analysis_movement"
    _comp_pcode = low.replace(" ", "")
    if ("stock and sales analysis" in low and "p.code" in low
            and "cls.stk" in _comp_pcode and "s.ret" in _comp_pcode
            and "adj." in _comp_pcode):
        return "klm_stock_sales_analysis_pcode"

    return "generic"

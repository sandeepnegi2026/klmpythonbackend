import re

SUBTOTAL_RE = re.compile(
    r"^\s*(total|sub.?total|grand total|page total|sales amount|qty .*total|amount .*total|"
    r"\*\* total|total of|last \d+ months|quantity|value in rs|net amount|total net|"
    r"bills:|purchase detail|purchase amount|free amount|closing amount|order amount|"
    r"total amount|bill no\.|o/s:|pending|authorized|for |powered|print health qrcode|marg erp)",
    re.I,
)

SKIP_RE = re.compile(
    r"^(stock & sales|stock and sale|stock statement|monthly sales|product stock report|"
    r"item description|item cd|opening|name\s+pack|product\s+opening|srno|sr\.?no|"
    r"company|mfg|from|vendor|contact|gstin|fssai|phone|licence|division|"
    r"^\d+/\d+$|page \d|continued|---+|===+|report for|reorder|sapcode|"
    r"non moving|purchase detail|supplier name|^\s*$)",
    re.I, 
)

DATE_RE = re.compile(
    r"(?P<start>\d{1,2}[-/]\w{2,3}[-/]?\d{2,4})\s*(?:-|to|\|)\s*(?P<end>\d{1,2}[-/]\w{2,3}[-/]?\d{2,4})",
    re.I,
)



NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?\.?$|^-$|^-----$")
EXP_RE = re.compile(r"^\d{1,2}/\d{2,4}$")
PACK_RE = re.compile(
    r"^(?:\d+(?:\.\d+)?\s*)?(?:ML|GM|GMS|MG|TAB|CAP|SYP|CREAM|LOTION|PCS|BOX|KIT|SOAP|"
    r"SACHET|OINT|DROP|DROPS|1\*\d+|\d+'?S|G|TUBE|SUSP|NOS|STR|LOT|PES|CRE|SOA)$",
    re.I,
)

LAYOUT_LABELS = {
    "marg_sales_stock_statement": "Marg Sales & Stock Statement (Op/Receipt/Issue/Closing Qty+Value; WIDE adds ReturnToCOM/RetFromCustomer/Expiry) — NARROW+WIDE, positional",
    "marg_stock_sales_expiry_positional": "Marg/MVGold Stock and Sales Statement (Opst/Purc/S.R./Sale+Val/P.R./Exp+Non-Mov/Closing+Val/Near.Exp, 14-col positional, per-division)",
    "klm_stock_sales_analysis_movement": "KLM Stock & Sales Analysis (division-banded 11-col movement: Opening/Purchase+Free/P.Return+Free/Sale+Free/S.Return+Free/Others/Closing, qty-only)",
    "stock_opbal_free_expiry": "KLM Sales & Stock Statement (Op.Bal/Receipt/Total/Issue/FreeQ/Expiry/Closing, qty-only)",
    "stock_ss_analysis_sret_others": "KLM Stock And Sales Analysis (Opening/Purchase/S.Return/Others-in/SubTotal/Sale/P.Return/Others-out/Closing, 9-col movement, dashes=nil)",
    "klm_ss_statement_receive_close": "KLM Stock & Sales Statement (Receive/Close, 2-page)",
    "stock_sales_statement_adjmt_positional": "STOCK & SALES STATEMENT (SREE SUPREME/ANANDH DOSPrinter; grouped OPENING/RECEIPT/SALES-LAST-QTY-FREE/ADJMT/CLOSING-QTY-FREE-VALUE, positional, dashes=nil)",
    "stock_oric_receipt_qtyonly": "Marg Stock & Sales Analysis (Opening/Issue/Closing qty+value pairs, RECEIPT qty-only) — AMRITA COSMOCOR",
    "swil_recv_issue_stock": "SwilERP Sales & Stock Statement — 9-col Op.Bal/Receipt/Retrn/Total/Issue/Retrn/Closing/Dump/Near (JAY SHREE)",
    "klm_stock_sales_month_tots": "KLM Stock & Sales Report (Month) — TotS/Sale_Val dialect: Op.Qt/Purch/Free/C_Sal/Free/Repl/Adj/Tot.S/Sale_Val positional (VASAN, per-division)",
    "purani_mfr_stock_sales_pdf": "PURANI HOSPITAL SUPPLIES MFR Stock & Sales (HTML-print PDF, positional)",
    "klm_stock_sales_month_netstock": "KLM Stock & Sales Report (Month) — NetStock dialect: Opening/Pure/ILast/Sale/Free/Rpl/Total/NetStockVal/SaleNet@Pur positional (BIOLEND)",
    "klm_stock_sales_month_rcpt": "KLM Stock & Sale Report (Month) — Rcpt dialect: OpStk/Rcpt/sales/Cl.S/StkValu/SalValu positional (SHIVASAKTHI)",
    "klm_stock_sales_analysis_pcode": "PRABHAT AGENCY — KLM Stock & Sales Analysis (P.Code, text)",
    "klm_stock_sales_small_pdf": "KLM Stock Sales Statement (Small) — Rate/Openin/Reciept/Sales/Free/SalesRt/Closing positional (MUDRAA/WARAD, wrapped)",
    "medichem_ss_expiry": "MEDICHEM Stock & Sales Statement — Opening/Sales/Purchase/Closing + Expiry (14-token per-division)",
    "meyon_prevmonth_stock": "MEYON DRUGS Stock Statement (Prev.month Sales/Rate/Op_Stk/Rcpts/P.Ret/Sales/Hos.Sal/Brk/Repl/Cl_Stk/Value, positional per-division)",
    "smartpharma_sas": "SmartPharma360 Stock And Sales Report (Open/Pur/Sales/SaleRet/Closing Qty+Value pairs, KLM, SRI BABA)",
    "csquare_manufacturerwise_stock_sales": "UNIVERSAL DRUG LINES — C-Square Manufacturerwise Stock and Sales (trailing-8 anchor)",
    "medivision_stock_sales": "MediVision Platinum — Stock and Sales (Op/Purc/Scm/Sale/Scm/Closing + values, positional, PyMuPDF)",
    "central_stock_sales": "CENTRAL AGENCIES (BlueFox) Stock And Sales Report (dense 14-col LMS/Op/Pur+F/Sale+F/Repl/Ret.BR/E/Adj/SaleValue/Bal.Qty+Val, KLM division-banded)",
    "medtraders_sales_stock_statement": "Sales & Stock Statement (Medicine Traders / SwilERP)",
    "stock_qoh_returns": "KLM Stock & Sales Statement Internal New (Ostk/Purc/Sale/SRet/PRet/Qoh+Value)",
    "swil_stock_lastpurc": "SwilERP Sales & Stock Statement (Op.Bal/Receipt/LastPurc-date/Total/Issue/Closing/Dump)",
    "stock_open_rec_adj_close": "Stock & Sales Statement (Open/Rec/Adj-/Adj+/Total/Sales/Close/Ord.Qty, dot-matrix)",
    "stock_open_purch_miscout": "KLM Stock & Sales Statement (Purticular/Open/Purch/SalesRet/Sales&DC/Misc.Out/Close + Closing/Sales Value)",
    "klm_stock_sales_month_repq": "KLM Stock & Sales Report (Month) — RepQ dialect: OpSt/PurQ/Sale/Free/RepQ/Stock/StockValue positional (JEYANTHI)",
    "stock_batchwise_statement": "Stock & Sales Statement (batch-wise: Product/Packing/BATCH/EXP/Opening/Receipts/Total/Sales/Closing Stock/Closing Value, KLM division-banded)",
    "klm_closing_stock_report": "KLM Closing Stock Report (SNO/Item/Pack/OpStk/PurQty+Value/SaleQty+Value/Free/ClStock+Value, positional)",
    "marg_sale_closing_pdf": "Marg Stock & Sales Analysis (reduced Sale/Closing Qty+Value pairs, KLM division bands + supplier register excluded)",
    "klm_stock_sale_prvsa": "KLM Stock & Sale Report (OpStk/Purch/PrvSa/Sales/Adj/Cl.St + P.price/Sales Valu, positional)",
    "marg_monthly_ss_statement_pdf": "Marg/KLM Monthly Stock & Sales Statement (Open/Pur/GoodsRet/Sale/PurcRet/Balance, positional)",
    "stock_open_rcpts_dualsales_pdf": "KLM Stock Report (Open/Receipt/L.Sales/Cur.Sls/Pur.Rtn/Sls.Rtn/Clos Qty+Amt, positional)",
    "klm_stock_sales_month": "KLM Stock & Sales Report (Month) \u2014 OpSt/Pur/Sale/Free/Adj/Cl.S positional (per-division)",
    "saleable_stock_qf": "Saleable Stock Report (pipe-delimited Opn/Rec/Issue/Bal Q+F)",
    "pharmassist_stock_sale": "PharmAssist (C-Square) Stock & Sale Report (page-split Op/Pur/Sale/Bal, positional)",
    "pharmassist_stock_sale_single": "PharmAssist (C-Square) Stock & Sale Report (single-page wide Apr/Mar/Op/Pur/SP/Sale/SS/.../Bal/BVal/SVal, positional)",
    "stock_sale_closing_pairs": "Marg Stock & Sales Analysis (Sale/Closing Qty+Value pairs)",
    "klm_stock_sales_combined_pdf": "KLM Stock Sales Statement (Combined) \u2014 Prev.Sale/Open/Pur/Total Sale/Adj./Total Closing (positional, wrapped)",
    "prompt_dstk_free_pdf": "Prompt ERP Stock Statement (Datewise) \u2014 free-carrying KLM variant (OpStk/Pur+Free/Sales+Free+Amt/ClStk+Amt, positional)",
    "marg_movement_detail_sparse": "Marg Stock & Sales Analysis (movement detail, qty only, blank-omitted/sparse, positional)",
    "marg_ss_statement_detailed": "Marg Stock & Sales Statement Detailed (Code+O.Bal/Purc/S.Ret/Sales/P.Ret/ClBal/Cl.Value)",
    "simple4": "Busy/Tally Simple4",
    "qty_value_total": "Qty+Value Pairs with Total Column",
    "value_pairs": "Marg Qty-Value Pairs",
    "marg_stock_summary": "Marg Stock Summary (Open/Pur/Ret/Receipts/Sales/Ret/Issue/Balance)",
    "stock_open_pur_sale_free_current": "KLM Stock & Sales (Code/Open/Pur/Sale/Free/Current/Amount/Closing)",
    "marg_stock_analysis_full": "Marg Stock & Sales Analysis (14-col Open/Pur/S-R/Repl/Total/Sales/Sample/P-R/Closing + M.Exp)",
    "marg_stock_ava_bval_sval": "Marg Stock And Sales Analysis (AVA/Apr/OP.BAL/PUR./PR./ADJ./SR./B.Sale/SALE/BAL + BVAL/SVAL, positional, MALU MEDICO)",
    "pharmassist_mfac": "PharmAssist (C-Square) Stock & Sales Mfac Group Wise (positional)",
    "klm_venus_opstk_crqty": "Venus KLM Stock & Sale Statement (page-split OpStk/P.Qty/P.Sch/S.Qty/S.Sch/CrQty | ClStk/ClVal, glyph-descrambled positional)",
    "dahod_stock_sale_stmt": "DAHOD PHARMAKON Stock & Sale Statement (SINGLE-page OpStk/P.Qty/P.Val/P.Sch/S.Qty/S.Sch/S.Val/CrQty/ClStk/ClVal/Order, right-edge x1 positional)",
    "marg_stock_recd_issued": "Marg Qty-only Stock & Sales (Opening/Recd/Issued/Cls, positional)",
    "marg_stock_long": "Marg Long Stock Movements",
    "marg_qty_value_wide": "Marg Qty-Value Wide",
    "stock_simple_7col": "Simple Name/Pack/Open/Pur/Sales/Close",
    "marg_lms_simple": "Marg LMS Simple",
    "stock_rate_amount": "Rate + Amount Columns",
    "dahod_marg": "Marg Item-Code Register",
    "stock_receipt_replace": "Receipt/Replace Statement",
    "pharma_bytes_itemcode": "Pharma Bytes Item-Code",
    "saurashtra_monthly": "Logic ERP Monthly Sales & Stock",
    "saurashtra_ss_report": "Logic ERP Monthly SS Report",
    "venus_stock_statement": "Venus Stock Statement",
    "marg_opstk_statement": "Marg OpStk Statement",
    "marg_bordered": "Marg Bordered Table",
    "marg_web_stock": "Marg Web Stock Report",
    "prompt_bordered": "Prompt ERP Bordered",
    "prompt": "Prompt ERP Text Statement",
    "prompt_datewise_favourite": "Prompt ERP Stock Statement (Datewise) — 4 pure-qty OpStk/Pur/Sales/ClStk + Amount + A3Mn/Favourite (DEV MEDICAL)",
    "pks_data": "PKS Data ERP Stock Statement",
    "technomax_stock": "Technomax Stock Statement",
    "kluster_stock": "Kluster Software",
    "dolphin_stock": "Dolphin ERP Stock Statement",
    "toreo_stock": "Toreo ERP Stock Statement",
    "siva_stock": "Siva Software Stock Report",
    "stock_qoh": "KLM Stock & Sales Statement (Qoh)",
    "stock_open_pur_sale_amt": "KLM Stock Register (Open/Pur/Sale/Amount)",
    "stock_gdin": "KLM Stock & Sale (Gd.In / Gd.Out)",
    "stock_oric_pairs": "Marg Stock & Sales Analysis (Qty/Value pairs)",
    "disa_opbal_receipt_total_issue": "DISA Stock & Sales Statement (Op.Bal/Receipt/Issue)",
    "capital_stock_sale_stmt": "KLM Sales & Stock Statement (Op.Bal/Receipt/Total/Issue/Closing, qty-only, CAPITAL PHARMA)",
    "swil_stock_transfer": "SwilERP Sales & Stock Statement (Op/Receipt/Transin/Total/Issue/TranOut/Closing Qty+Value + Dump, BIDYA PHARMA)",
    "marg_pds_replace": "Marg Product-Description Receipts (Replace+)",
    "marg_open_pur_free_sale": "Marg Stock & Sales Analysis (Open/Pur/Free/Sale)",
    "marg_movement_detail": "Marg Stock & Sales Analysis (movement detail, qty only)",
    "saraswati_lstsl": "Busy Stock & Sales Report (LstSL/LstMove)",
    "stock_lstsl": "Busy Stock & Sales Report (7-col LstSL, no Stk.Value)",
    "product_wise_stock_sale_profit": "Marg Product Wise Stock and Sale -With Profit (positional)",
    "nagendra_rate_pairs": "Stock Statement (Rate + Qty/Value pairs)",
    "swastik_particulars": "Particulars/Misc Stock Statement",
    "marg_opqty": "Marg Stock & Sale Report (OPQTY/B_QTY)",
    "stock_op_pur_total_sale_close": "Stock Statement (Op/Pur/Total/Sale/Close)",
    "stock_received_issued": "Stock & Sales (Opening/Received/Issued/Closing)",
    "stock_in_out_statement": "Stock Statement (Code + Stock-In/Out + monthly cols)",
    "generic": "Generic Fallback",
}

import re

SUBTOTAL_RE = re.compile(
    r"^\s*(total|sub.?total|grand total|page total|print health qrcode|marg erp|"
    r"opening value|closing value|sales value|receipt value|order value|last month sales|"
    r"report date|sales$|mg\d+|"
    r"qty\s+total|amount\s+total|qty\s+grand\s+total|amount\s+grand\s+total|"
    r"for\s+\w|authorised|authorized)\b",
    re.I,
)



LAYOUT_LABELS = {
    "klm_op_pi_sale_cl_value_xlsx": "KLM Stock & Sales (OP/PI/Sale/CLQty qty+value, no-OUT) — DHRUVI klm.xlsx",
    "gs_stock_sales_wide27_xlsx": "G.S. DISTRIBUTORS — KLM Stock & Sales Statement (wide 28-col OPSTK/PURC/SALE/STOCK + PURCV/SALEV grid)",
    "stock_sales_analysis_oic_xlsx": "KLM Stock & Sales Analysis (single-col Opening/Receipt/Issue/Closing) — AMETOMBI",
    "stock_sales_analysis_wide_xlsx": "KLM Stock & Sales Analysis (single-col wide Open/Purchase/SaleRet/Total/Sales/PurchRet/Closing) — KRISHNA PHARMA",
    "central_stock_and_sales_xls": "CENTRAL DISTRIBUTORS — KLM Stock And Sales Report (exact-header .xls)",
    "klm_mfr_op_pq_clqty_xlsx": "KLM MFR Wise Stock & Sales (Op/PQ/Fr/SQ/Cl Qty, JAYANTHI)",
    "purani_mfr_stock_sales": "PURANI HOSPITAL SUPPLIES — MFR Stock and Sales Report (18-col HTML-in-.xls, current-month per division)",
    "klm_venus_opstk_crqty": "KLM Venus Stock & Sale (OpStk/CrQty scheme, banded)",
    "marg_sale_closing_grid_xlsx": "Marg Stock & Sales Analysis (clean Sale/Closing qty+value grid, BALLRI)",
    "marg_stock_analysis_wide_xlsx": "Marg Stock & Sales Analysis (spelled-out wide 2-row grid, arrow separators)",
    "klm_sale_dtl_xlsx": "DEEPA/KLM SALE_DTL Stock & Sales (OP_BAL/CL_BAL abbrev headers)",
    "klm_op_pi_clqty_xlsx": "KLM Stock & Sales (OP/PI/Sale/ST(Out)/CLQty, DHRUVI)",
    "marg_sale_closing_xlsx": "Marg Stock & Sales Analysis (reduced Sale/Closing qty+value)",
    "klm_sale_stock_stmt": "    \"klm_sale_stock_stmt\": \"KLM Sale & Stock Statement (OpStk/Branch Return/StkAdj, qty-only)\",",
    "klm_stock_and_sale": "\"klm_stock_and_sale\": \"KLM Stock And Sale (SP/SS free + SRet/TRR/TRI + Cls.Stk)\",",
    "klm_lifecare_stock": "\"klm_lifecare_stock\": \"KLM Stock And Sales Report(Month) (LIFE CARE / YOGIRAM)\",",
    "medicine_klm_detailed": "\"medicine_klm_detailed\": \"SwilERP Sales & Stock Statement (MEDICINE TRADERS KLM, dual Free-Qty)\",",
    "klm_op_pr_sl_stock": "    \"klm_op_pr_sl_stock\": \"KLM Stock Statement (OP_STK/PR_REC/TOT_REC/SL_ISS/CL_STK)\",",
    "marg_monthly_ss_statement_xlsx": "\"marg_monthly_ss_statement_xlsx\": \"Marg Monthly Stock & Sales Statement (KLM Palanpur)\",",
    "stock_open_rcpts_dualsales_xlsx": "\"stock_open_rcpts_dualsales_xlsx\": \"KLM Stock (Open/Rcpts/L.Sales/Cur.Sls + split Clos.Qty&Amt)\",",
    "marg_stock_analysis_qv": "\"marg_stock_analysis_qv\": \"Marg Stock & Sales Analysis (single-column qty+value)\",",
    "marg_stock_open_rcpt_issue_xls": "Marg Stock & Sales Analysis (single-column Open/Receipt/Issue/Closing qty+value, BURIMAA)",
    "marg_stock_analysis_qv_grid": "Marg Stock & Sales Analysis (Open/Receipt/Issue/Closing+Dump qty+value grid, DERMA DISTRIBUTORS)",
    "marg_stock_analysis_qv_dumpext": "Marg Stock & Sales Analysis (merged single-column Open/Receipt/Issue/Closing+Dump+extra, D.S.PHARMA)",
    "klm_stock_sales_saleamt": "KLM Stock & Sales (NAME/OPEN/PURCHASE/SALES/SALEAMT/CLOSING/CLOSEAMT, TIRUPATI)",
    "stock_op_rec_iss_clos_grid": "Stock Open/Receipt/Issue/Closing qty+value grid (op_stock/rec_qty/iss_qty/clos_qty, CHOUDHARY)",
    "stock_op_pur_total_cl_xlsx": "Sales && Stock Statement (OP/PUR/Total=Sales/CL qty+amt grid, GARG)",
    "marg_stock_sales_lms_xls": "Marg Stock and Sales Report (offset 2-row header, LMS/Opening/Purchase/Sales/Closing, CHAITANYA)",
    "klm_stock_sales_combined_xlsx": "KLM Stock Sales Statement (Combined)",
    "prompt_dstk_free_xlsx": "\"prompt_dstk_free_xlsx\": \"Prompt ERP Stock Statement (Datewise) \u2014 KLM\",",
    "marg_stock_wide": "Marg ERP Wide Stock Report",
    "venus_stock_excel": "Venus Stock Excel",
    "marg_opstk_curstk": "Marg OpStk/CurStk Statement",
    "html_stock": "HTML Stock Export",
    "infosoft_stock": "Visual Infosoft Batch-wise Stock",
    "profit_maker": "Profit Maker ERP Stock Statement",
    "marg_erp9_movement": "Marg ERP 9+ Stock & Sales Analysis",
    "marg_stock_sale_band": "Marg Wide Stock & Sales Band",
    "klm_dstk_stock": "KLM DSTK Stock & Sales (OPSTK/PURC/STOCK)",
    "marg_stock_analysis_text": "Marg Stock & Sales Analysis (single-column text)",
    "tabular": "Generic Tabular",
}

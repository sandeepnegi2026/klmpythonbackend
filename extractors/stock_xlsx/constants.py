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

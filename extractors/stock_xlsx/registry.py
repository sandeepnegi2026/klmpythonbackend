from extractors.stock_xlsx.header_fields import detect_header_row
from extractors.stock_xlsx.layouts.klm_op_pi_sale_cl_value_xlsx import parse_klm_op_pi_sale_cl_value_xlsx
from extractors.stock_xlsx.layouts.stock_sales_analysis_oic_xlsx import parse_stock_sales_analysis_oic_xlsx
from extractors.stock_xlsx.layouts.stock_sales_analysis_wide_xlsx import parse_stock_sales_analysis_wide_xlsx
from extractors.stock_xlsx.layouts.gs_stock_sales_wide27_xlsx import parse_gs_stock_sales_wide27_xlsx
from extractors.stock_xlsx.layouts.marg_opstk_curstk import parse_marg_opstk_curstk
from extractors.stock_xlsx.layouts.marg_stock_wide import parse_marg_stock_wide
from extractors.stock_xlsx.layouts.tabular import records_from_rows
from extractors.stock_xlsx.layouts.venus_stock_excel import parse_venus_stock_excel
from extractors.stock_xlsx.layouts.infosoft_stock import parse_infosoft_stock
from extractors.stock_xlsx.layouts.profit_maker import parse_profit_maker
from extractors.stock_xlsx.layouts.fawin_stock import parse_fawin_stock
from extractors.stock_xlsx.layouts.marg_erp9_movement import parse_marg_erp9_movement
from extractors.stock_xlsx.layouts.marg_stock_sale_band import parse_marg_stock_sale_band
from extractors.stock_xlsx.layouts.klm_dstk_stock import parse_klm_dstk_stock
from extractors.stock_xlsx.layouts.marg_designer_compute_stock import parse_marg_designer_compute_stock
from extractors.stock_xlsx.layouts.marg_stock_analysis_text import parse_marg_stock_analysis_text
from extractors.stock_xlsx.layouts.klm_detailed_stock import parse_klm_detailed_stock
from extractors.stock_xlsx.layouts.klm_mfac_group_wise_stock import parse_klm_mfac_group_wise_stock
from extractors.stock_xlsx.layouts.klm_opstk_apr_may_curstk_xls import parse_klm_opstk_apr_may_curstk_xls

from extractors.stock_xlsx.layouts.marg_monthly_ss_statement_xlsx import parse_marg_monthly_ss_statement_xlsx
from extractors.stock_xlsx.layouts.stock_open_rcpts_dualsales_xlsx import parse_stock_open_rcpts_dualsales_xlsx
from extractors.stock_xlsx.layouts.marg_stock_analysis_qv import parse_marg_stock_analysis_qv
from extractors.stock_xlsx.layouts.marg_stock_open_rcpt_issue_xls import parse_marg_stock_open_rcpt_issue_xls
from extractors.stock_xlsx.layouts.marg_stock_analysis_qv_grid import parse_marg_stock_analysis_qv_grid
from extractors.stock_xlsx.layouts.marg_stock_analysis_qv_dumpext import parse_marg_stock_analysis_qv_dumpext
from extractors.stock_xlsx.layouts.klm_stock_sales_saleamt import parse_klm_stock_sales_saleamt
from extractors.stock_xlsx.layouts.stock_op_rec_iss_clos_grid import parse_stock_op_rec_iss_clos_grid
from extractors.stock_xlsx.layouts.marg_stock_sales_lms_xls import parse_marg_stock_sales_lms_xls
from extractors.stock_xlsx.layouts.klm_stock_sales_combined_xlsx import parse_klm_stock_sales_combined_xlsx
from extractors.stock_xlsx.layouts.prompt_dstk_free_xlsx import parse_prompt_dstk_free_xlsx

from extractors.stock_xlsx.layouts.klm_sale_stock_stmt import parse_klm_sale_stock_stmt
from extractors.stock_xlsx.layouts.klm_stock_and_sale import parse_klm_stock_and_sale
from extractors.stock_xlsx.layouts.klm_lifecare_stock import parse_klm_lifecare_stock
from extractors.stock_xlsx.layouts.medicine_klm_detailed import parse_medicine_klm_detailed
from extractors.stock_xlsx.layouts.klm_op_pr_sl_stock import parse_klm_op_pr_sl_stock

from extractors.stock_xlsx.layouts.marg_sale_closing_xlsx import parse_marg_sale_closing_xlsx

from extractors.stock_xlsx.layouts.klm_venus_opstk_crqty import parse_klm_venus_opstk_crqty

from extractors.stock_xlsx.layouts.marg_sale_closing_grid_xlsx import parse_marg_sale_closing_grid_xlsx
from extractors.stock_xlsx.layouts.marg_stock_analysis_wide_xlsx import parse_marg_stock_analysis_wide_xlsx
from extractors.stock_xlsx.layouts.klm_sale_dtl_xlsx import parse_klm_sale_dtl_xlsx
from extractors.stock_xlsx.layouts.klm_op_pi_clqty_xlsx import parse_klm_op_pi_clqty_xlsx
from extractors.stock_xlsx.layouts.stock_op_pur_total_cl_xlsx import parse_stock_op_pur_total_cl_xlsx

from extractors.stock_xlsx.layouts.central_stock_and_sales_xls import parse_central_stock_and_sales_xls
from extractors.stock_xlsx.layouts.klm_mfr_op_pq_clqty_xlsx import parse_klm_mfr_op_pq_clqty_xlsx
from extractors.stock_xlsx.layouts.klm_stock_sale_gdout_xlsx import parse_klm_stock_sale_gdout
from extractors.stock_xlsx.layouts.marg_sale_closing_text_xlsx import parse_marg_sale_closing_text_xlsx
from extractors.stock_xlsx.layouts.marg_stock_ss_full_movement_xls import parse_marg_stock_ss_full_movement_xls

# --- 15 July RED-cluster parsers (batch 2) ---------------------------------
from extractors.stock_xlsx.layouts.r15_klm_ss_pfree_purret_marapr_curstk_xls import parse_klm_ss_pfree_purret_marapr_curstk_xls
from extractors.stock_xlsx.layouts.r15_prompt_dstk_salesfree_order_xls import parse_prompt_dstk_salesfree_order_xls
from extractors.stock_xlsx.layouts.r15_marg_stock_wide_multival_xls import parse_marg_stock_wide_multival_xls
from extractors.stock_xlsx.layouts.r15_klm_opstk_psch_in_ssch_out_stock_xls import parse_klm_opstk_psch_in_ssch_out_stock_xls
from extractors.stock_xlsx.layouts.r15_klm_ss_detail_unit1unit2_intransit_xls import parse_klm_ss_detail_unit1unit2_intransit_xls
from extractors.stock_xlsx.layouts.r15_stock_receipt_issue_closing_grid_xls import parse_stock_receipt_issue_closing_grid_xls
from extractors.stock_xlsx.layouts.r15_klm_ss_analysis_oic_dualclose_grid_xls import parse_klm_ss_analysis_oic_dualclose_grid_xls
from extractors.stock_xlsx.layouts.r15_marg_sales_stock_summary_opstock_instock_outstock_xls import parse_marg_sales_stock_summary_opstock_instock_outstock_xls
from extractors.stock_xlsx.layouts.r15_klm_monthly_ss_opening_inward_sales_other_closing_xls import parse_klm_monthly_ss_opening_inward_sales_other_closing_xls
from extractors.stock_xlsx.layouts.r15_marg_normal_ss_open_recp_othr_sales_clsg_qtyonly_xls import parse_marg_normal_ss_open_recp_othr_sales_clsg_qtyonly_xls
from extractors.stock_xlsx.layouts.r15_klm_ss_pfree_purret_aprmay_sfree_adj_curstk_xls import parse_klm_ss_pfree_purret_aprmay_sfree_adj_curstk_xls
from extractors.stock_xlsx.layouts.r15_klm_ss_stmt_prod_desc_totrecv_replace_xls import parse_klm_ss_stmt_prod_desc
from extractors.stock_xlsx.layouts.r15_klm_ss_paired_opstk_pfree_sfree_curstk_xls import parse_klm_ss_paired_opstk_pfree_sfree_curstk_xls
from extractors.stock_xlsx.layouts.r15_klm_item_recd_issued_sreturn_preturn_free_xls import parse_klm_item_recd_issued_sreturn_preturn_free_xls
from extractors.stock_xlsx.layouts.r15_klm_venus_op_pur_sp_sale_ss_cr_db_adj_cstk_xls import parse_klm_venus_op_pur_sp_sale_ss_cr_db_adj_cstk_xls

PARSERS = {
    # --- 15 July RED-cluster parsers (batch 2) ---
    "r15_klm_ss_pfree_purret_marapr_curstk_xls": parse_klm_ss_pfree_purret_marapr_curstk_xls,
    "prompt_dstk_salesfree_order_xls": parse_prompt_dstk_salesfree_order_xls,
    "marg_stock_wide_multival_xls": parse_marg_stock_wide_multival_xls,
    "r15_klm_opstk_psch_in_ssch_out_stock_xls": parse_klm_opstk_psch_in_ssch_out_stock_xls,
    "klm_ss_detail_unit1unit2_intransit_xls": parse_klm_ss_detail_unit1unit2_intransit_xls,
    "r15_stock_receipt_issue_closing_grid_xls": parse_stock_receipt_issue_closing_grid_xls,
    "r15_klm_ss_analysis_oic_dualclose_grid_xls": parse_klm_ss_analysis_oic_dualclose_grid_xls,
    "marg_sales_stock_summary_opstock_instock_outstock_xls": parse_marg_sales_stock_summary_opstock_instock_outstock_xls,
    "klm_monthly_ss_opening_inward_sales_other_closing_xls": parse_klm_monthly_ss_opening_inward_sales_other_closing_xls,
    "marg_normal_ss_open_recp_othr_sales_clsg_qtyonly_xls": parse_marg_normal_ss_open_recp_othr_sales_clsg_qtyonly_xls,
    "klm_ss_pfree_purret_aprmay_sfree_adj_curstk_xls": parse_klm_ss_pfree_purret_aprmay_sfree_adj_curstk_xls,
    "klm_ss_stmt_prod_desc": parse_klm_ss_stmt_prod_desc,
    "klm_ss_paired_opstk_pfree_sfree_curstk_xls": parse_klm_ss_paired_opstk_pfree_sfree_curstk_xls,
    "r15_klm_item_recd_issued_sreturn_preturn_free_xls": parse_klm_item_recd_issued_sreturn_preturn_free_xls,
    "r15_klm_venus_op_pur_sp_sale_ss_cr_db_adj_cstk_xls": parse_klm_venus_op_pur_sp_sale_ss_cr_db_adj_cstk_xls,
    "klm_mfac_group_wise_stock": parse_klm_mfac_group_wise_stock,
    "klm_opstk_apr_may_curstk_xls": parse_klm_opstk_apr_may_curstk_xls,
    "klm_stock_sale_gdout_xlsx": parse_klm_stock_sale_gdout,
    "marg_sale_closing_text_xlsx": parse_marg_sale_closing_text_xlsx,
    "marg_stock_ss_full_movement_xls": parse_marg_stock_ss_full_movement_xls,
    "klm_op_pi_sale_cl_value_xlsx": parse_klm_op_pi_sale_cl_value_xlsx,
    "stock_sales_analysis_oic_xlsx": parse_stock_sales_analysis_oic_xlsx,
    "stock_sales_analysis_wide_xlsx": parse_stock_sales_analysis_wide_xlsx,
    "gs_stock_sales_wide27_xlsx": parse_gs_stock_sales_wide27_xlsx,
    "central_stock_and_sales_xls": parse_central_stock_and_sales_xls,
    "klm_mfr_op_pq_clqty_xlsx": parse_klm_mfr_op_pq_clqty_xlsx,
    "stock_op_pur_total_cl_xlsx": parse_stock_op_pur_total_cl_xlsx,
    "klm_venus_opstk_crqty": parse_klm_venus_opstk_crqty,
    "marg_sale_closing_grid_xlsx": parse_marg_sale_closing_grid_xlsx,
    "marg_stock_analysis_wide_xlsx": parse_marg_stock_analysis_wide_xlsx,
    "klm_sale_dtl_xlsx": parse_klm_sale_dtl_xlsx,
    "klm_op_pi_clqty_xlsx": parse_klm_op_pi_clqty_xlsx,
    "marg_sale_closing_xlsx": parse_marg_sale_closing_xlsx,
    "klm_sale_stock_stmt": parse_klm_sale_stock_stmt,
    "klm_stock_and_sale": parse_klm_stock_and_sale,
    "klm_lifecare_stock": parse_klm_lifecare_stock,
"medicine_klm_detailed": parse_medicine_klm_detailed,
    "klm_op_pr_sl_stock": parse_klm_op_pr_sl_stock,
"marg_monthly_ss_statement_xlsx": parse_marg_monthly_ss_statement_xlsx,
    "stock_open_rcpts_dualsales_xlsx": parse_stock_open_rcpts_dualsales_xlsx,
"marg_stock_analysis_qv": parse_marg_stock_analysis_qv,
    "marg_stock_open_rcpt_issue_xls": parse_marg_stock_open_rcpt_issue_xls,
    "marg_stock_analysis_qv_grid": parse_marg_stock_analysis_qv_grid,
    "marg_stock_analysis_qv_dumpext": parse_marg_stock_analysis_qv_dumpext,
    "klm_stock_sales_saleamt": parse_klm_stock_sales_saleamt,
    "stock_op_rec_iss_clos_grid": parse_stock_op_rec_iss_clos_grid,
    "marg_stock_sales_lms_xls": parse_marg_stock_sales_lms_xls,
    "klm_stock_sales_combined_xlsx": parse_klm_stock_sales_combined_xlsx,
    "prompt_dstk_free_xlsx": parse_prompt_dstk_free_xlsx,
    "marg_stock_analysis_text": parse_marg_stock_analysis_text,
    "klm_detailed_stock": parse_klm_detailed_stock,
    "marg_stock_wide": parse_marg_stock_wide,
    "venus_stock_excel": parse_venus_stock_excel,
    "marg_opstk_curstk": parse_marg_opstk_curstk,
    "infosoft_stock": parse_infosoft_stock,
    "profit_maker": parse_profit_maker,
    "fawin_stock": parse_fawin_stock,
    "marg_erp9_movement": parse_marg_erp9_movement,
    "marg_stock_sale_band": parse_marg_stock_sale_band,
    "klm_dstk_stock": parse_klm_dstk_stock,
    "marg_designer_compute_stock": parse_marg_designer_compute_stock,
}


def parse_rows(rows, layout, header_row_hint=None):
    if layout in PARSERS:
        return PARSERS[layout](rows)
    header_idx = detect_header_row(rows, header_row_hint) if rows else None
    if header_idx is None:
        return [], {}
    return records_from_rows(rows, header_idx)

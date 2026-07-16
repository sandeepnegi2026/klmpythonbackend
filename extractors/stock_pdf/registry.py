from extractors.stock_pdf.layouts.dahod_marg import parse_dahod_marg
from extractors.stock_pdf.layouts.generic import parse_generic
from extractors.stock_pdf.layouts.marg_sales_stock_statement import parse_marg_sales_stock_statement
from extractors.stock_pdf.layouts.marg_stock_sales_expiry_positional import parse_marg_stock_sales_expiry_positional
from extractors.stock_pdf.layouts.stock_sales_statement_adjmt_positional import parse_stock_sales_statement_adjmt_positional
from extractors.stock_pdf.layouts.stock_oric_receipt_qtyonly import parse_stock_oric_receipt_qtyonly
from extractors.stock_pdf.layouts.klm_stock_sales_analysis_movement import parse_klm_stock_sales_analysis_movement
from extractors.stock_pdf.layouts.stock_opbal_free_expiry import parse_stock_opbal_free_expiry
from extractors.stock_pdf.layouts.stock_ss_analysis_sret_others import parse_stock_open_pur_sret_others_subtotal as parse_stock_ss_analysis_sret_others
from extractors.stock_pdf.layouts.klm_ss_statement_receive_close import parse_klm_ss_statement_receive_close
from extractors.stock_pdf.layouts.marg_lms_simple import parse_marg_lms_simple
from extractors.stock_pdf.layouts.marg_opstk_statement import parse_marg_opstk_statement
from extractors.stock_pdf.layouts.marg_qty_value_wide import parse_marg_qty_value_wide
from extractors.stock_pdf.layouts.marg_stock_long import parse_marg_stock_long
from extractors.stock_pdf.layouts.pharma_bytes_itemcode import parse_pharma_bytes_itemcode
from extractors.stock_pdf.layouts.saurashtra_monthly import parse_saurashtra_monthly
from extractors.stock_pdf.layouts.saurashtra_ss_report import parse_saurashtra_ss_report
from extractors.stock_pdf.layouts.qty_value_total import parse_qty_value_total
from extractors.stock_pdf.layouts.simple4 import parse_simple4
from extractors.stock_pdf.layouts.stock_rate_amount import parse_stock_rate_amount
from extractors.stock_pdf.layouts.stock_receipt_replace import parse_stock_receipt_replace
from extractors.stock_pdf.layouts.stock_simple_7col import parse_stock_simple_7col
from extractors.stock_pdf.layouts.value_pairs import parse_value_pairs
from extractors.stock_pdf.layouts.venus_stock_statement import parse_venus_stock_statement
from extractors.stock_pdf.layouts.pks_data import parse_pks_data
from extractors.stock_pdf.layouts.prompt import parse_prompt
from extractors.stock_pdf.layouts.prompt_datewise_favourite import parse_prompt_datewise_favourite
from extractors.stock_pdf.layouts.technomax import parse_technomax_stock
from extractors.stock_pdf.layouts.kluster_stock import parse_kluster_stock
from extractors.stock_pdf.layouts.dolphin import parse_dolphin_stock
from extractors.stock_pdf.layouts.toreo import parse_toreo_stock
from extractors.stock_pdf.layouts.siva_stock import parse_siva_stock
from extractors.stock_pdf.layouts.stock_qoh import parse_stock_qoh
from extractors.stock_pdf.layouts.stock_open_pur_sale_amt import parse_stock_open_pur_sale_amt
from extractors.stock_pdf.layouts.stock_gdin import parse_stock_gdin
from extractors.stock_pdf.layouts.stock_oric_pairs import parse_stock_oric_pairs
from extractors.stock_pdf.layouts.disa_opbal_receipt_total_issue import parse_disa_opbal_receipt_total_issue
from extractors.stock_pdf.layouts.capital_stock_sale_stmt import parse_capital_stock_sale_stmt
from extractors.stock_pdf.layouts.swil_stock_transfer import parse_swil_stock_transfer
from extractors.stock_pdf.layouts.swil_stock_company_summary import parse_swil_stock_company_summary
from extractors.stock_pdf.layouts.marg_pds_replace import parse_marg_pds_replace
from extractors.stock_pdf.layouts.marg_open_pur_free_sale import parse_marg_open_pur_free_sale
from extractors.stock_pdf.layouts.marg_movement_detail import parse_marg_movement_detail
from extractors.stock_pdf.layouts.saraswati_lstsl import parse_saraswati_lstsl
from extractors.stock_pdf.layouts.nagendra_rate_pairs import parse_nagendra_rate_pairs
from extractors.stock_pdf.layouts.swastik_particulars import parse_swastik_particulars
from extractors.stock_pdf.layouts.marg_opqty import parse_marg_opqty
from extractors.stock_pdf.layouts.stock_op_pur_total_sale_close import parse_stock_op_pur_total_sale_close
from extractors.stock_pdf.layouts.stock_received_issued import parse_stock_received_issued
from extractors.stock_pdf.layouts.klm_received_issued_stmt import parse_klm_received_issued_stmt
from extractors.stock_pdf.layouts.stock_in_out_statement import parse_stock_in_out_statement
from extractors.stock_pdf.layouts.marg_stock_summary import parse_marg_stock_summary
from extractors.stock_pdf.layouts.stock_open_pur_sale_free_current import parse_stock_open_pur_sale_free_current
from extractors.stock_pdf.layouts.marg_stock_analysis_full import parse_marg_stock_analysis_full
from extractors.stock_pdf.layouts.klm_stock_sales_analysis_free import parse_klm_stock_sales_analysis_free
from extractors.stock_pdf.layouts.pharmassist_mfac import parse_pharmassist_mfac
from extractors.stock_pdf.layouts.marg_stock_recd_issued import parse_marg_stock_recd_issued
from extractors.stock_pdf.layouts.klm_venus_opstk_crqty import parse_klm_venus_opstk_crqty
from extractors.stock_pdf.layouts.dahod_stock_sale_stmt import parse_dahod_stock_sale_stmt

from extractors.stock_pdf.layouts.klm_stock_sale_prvsa import parse_klm_stock_sale_prvsa
from extractors.stock_pdf.layouts.marg_monthly_ss_statement_pdf import parse_marg_monthly_ss_statement_pdf
from extractors.stock_pdf.layouts.stock_open_rcpts_dualsales_pdf import parse_stock_open_rcpts_dualsales_pdf
from extractors.stock_pdf.layouts.klm_stock_sales_month import parse_klm_stock_sales_month
from extractors.stock_pdf.layouts.saleable_stock_qf import parse_saleable_stock_qf
from extractors.stock_pdf.layouts.pharmassist_stock_sale import parse_pharmassist_stock_sale
from extractors.stock_pdf.layouts.pharmassist_stock_sale_single import parse_pharmassist_stock_sale_single
from extractors.stock_pdf.layouts.stock_sale_closing_pairs import parse_stock_sale_closing_pairs
from extractors.stock_pdf.layouts.klm_stock_sales_combined_pdf import parse_klm_stock_sales_combined_pdf
from extractors.stock_pdf.layouts.prompt_dstk_free_pdf import parse_prompt_dstk_free_pdf
from extractors.stock_pdf.layouts.marg_movement_detail_sparse import parse_marg_movement_detail_sparse
from extractors.stock_pdf.layouts.marg_ss_statement_detailed import parse_marg_ss_statement_detailed

from extractors.stock_pdf.layouts.klm_closing_stock_report import parse_klm_closing_stock_report
from extractors.stock_pdf.layouts.marg_sale_closing_pdf import parse_marg_sale_closing_pdf

from extractors.stock_pdf.layouts.medtraders_sales_stock_statement import parse_medtraders_sales_stock_statement
from extractors.stock_pdf.layouts.medivision_stock_sales import parse_medivision_stock_sales

from extractors.stock_pdf.layouts.stock_qoh_returns import parse_stock_qoh_returns
from extractors.stock_pdf.layouts.stock_open_rec_adj_close import parse_stock_open_rec_adj_close
from extractors.stock_pdf.layouts.swil_stock_lastpurc import parse_swil_stock_lastpurc
from extractors.stock_pdf.layouts.stock_open_purch_miscout import parse_stock_open_purch_miscout
from extractors.stock_pdf.layouts.klm_stock_sales_month_repq import parse_klm_stock_sales_month_repq
from extractors.stock_pdf.layouts.stock_batchwise_statement import parse_stock_batchwise_statement
from extractors.stock_pdf.layouts.central_stock_sales import parse_central_stock_sales
from extractors.stock_pdf.layouts.stock_lstsl import parse_stock_lstsl
from extractors.stock_pdf.layouts.product_wise_stock_sale_profit import (
    parse_product_wise_stock_sale_profit,
)

from extractors.stock_pdf.layouts.klm_stock_sales_month_netstock import parse_klm_stock_sales_month_netstock
from extractors.stock_pdf.layouts.klm_stock_sales_month_rcpt import parse_klm_stock_sales_month_rcpt
from extractors.stock_pdf.layouts.klm_stock_sales_analysis_pcode import parse_klm_stock_sales_analysis_pcode
from extractors.stock_pdf.layouts.klm_stock_sales_small_pdf import parse_klm_stock_sales_small_pdf
from extractors.stock_pdf.layouts.medichem_ss_expiry import parse_medichem_ss_expiry
from extractors.stock_pdf.layouts.meyon_prevmonth_stock import parse_meyon_prevmonth_stock
from extractors.stock_pdf.layouts.smartpharma_sas import parse_smartpharma_sas
from extractors.stock_pdf.layouts.csquare_manufacturerwise_stock_sales import parse_csquare_manufacturerwise_stock_sales
from extractors.stock_pdf.layouts.klm_stock_sales_month_tots import parse_klm_stock_sales_month_tots
from extractors.stock_pdf.layouts.purani_mfr_stock_sales_pdf import parse_purani_mfr_stock_sales_pdf
from extractors.stock_pdf.layouts.swil_recv_issue_stock import parse_swil_recv_issue_stock
from extractors.stock_pdf.layouts.marg_stock_ava_bval_sval import parse_marg_stock_ava_bval_sval

from extractors.stock_pdf.layouts.klm_lmsale_receipts_age import parse_klm_lmsale_receipts_age
from extractors.stock_pdf.layouts.klm_stock_sales_inout_expiry import parse_klm_stock_sales_inout_expiry
from extractors.stock_pdf.layouts.stock_unit_op_purc_sale_cl import parse_stock_unit_op_purc_sale_cl
from extractors.stock_pdf.layouts.stock_sale_stmt_stkad import parse_stock_sale_stmt_stkad
from extractors.stock_pdf.layouts.stock_opbal_issue_expiry_near import parse_stock_opbal_issue_expiry_near
from extractors.stock_pdf.layouts.stock_item_desc_oric_movement import parse_stock_item_desc_oric_movement
from extractors.stock_pdf.layouts.medivision_company_stock_sales import parse_medivision_company_stock_sales
from extractors.stock_pdf.layouts.prompt_datewise_amount_cols import parse_prompt_datewise_amount_cols

# --- 15 July RED-cluster parsers (batch 2) ---------------------------------
from extractors.stock_pdf.layouts.metro_sales_stock_statement_glyph import parse_metro_sales_stock_statement_glyph
from extractors.stock_pdf.layouts.r15_stock_qoh_paired_value import parse_stock_qoh_paired_value
from extractors.stock_pdf.layouts.r15_akshar_open_pur_free_total_sale_free_close import parse_akshar_open_pur_free_total_sale_free_close
from extractors.stock_pdf.layouts.r15_klm_stock_sales_marapr_positional import parse_r15_klm_stock_sales_marapr_positional
from extractors.stock_pdf.layouts.r15_klm_ss_qty_value_dualfree import parse_klm_ss_qty_value_dualfree
from extractors.stock_pdf.layouts.r15_monthly_ss_inward_other_closing import parse_r15_monthly_ss_inward_other_closing
from extractors.stock_pdf.layouts.r15_klm_pcode_opstk_psch_ssch_positional import parse_klm_pcode_opstk_psch_ssch_positional
from extractors.stock_pdf.layouts.r15_jayambe_monthly_ss_balance import parse_jayambe_monthly_ss_balance
from extractors.stock_pdf.layouts.r15_klm_lab_open_recv_sales_close_value_positional import parse_r15_klm_lab_open_recv_sales_close_value_positional
from extractors.stock_pdf.layouts.r15_klm_ss_month_totalstock_ilast_positional import parse_r15_klm_ss_month_totalstock_ilast_positional
from extractors.stock_pdf.layouts.r15_klm_ss_register_receipt_inst_gr_positional import parse_r15_klm_ss_register_receipt_inst_gr_positional
from extractors.stock_pdf.layouts.r15_klm_ss_prevlast_twopage_positional import parse_r15_klm_ss_prevlast_twopage_positional
from extractors.stock_pdf.layouts.r15_nu_srishyam_sales_stock_detail_tripage import parse_r15_nu_srishyam_sales_stock_detail_tripage
from extractors.stock_pdf.layouts.r15_klm_pharmaasia_code_open_recv_sales_close_dualvalue import parse_r15_klm_pharmaasia_code_open_recv_sales_close_dualvalue
from extractors.stock_pdf.layouts.r15_pharma_asia_simpleformat import parse_r15_pharma_asia_simpleformat
from extractors.stock_pdf.layouts.r15_smartpharma_reps_ostk_replace import parse_smartpharma_reps_ostk_replace
from extractors.stock_pdf.layouts.r15_klm_smartpharma_stocksale_tstock import parse_klm_smartpharma_stocksale_tstock
from extractors.stock_pdf.layouts.r15_medica_stock_apr_mar import parse_medica_stock_apr_mar
from extractors.stock_pdf.layouts.r15_medivision_stock_sales_addless import parse_r15_medivision_stock_sales_addless
from extractors.stock_pdf.layouts.r15_klm_ss_combined_pipe_flat import parse_klm_ss_combined_pipe_flat
from extractors.stock_pdf.layouts.r15_prompt_datewise_pack_free_inst import parse_prompt_datewise_pack_free_inst
from extractors.stock_pdf.layouts.r15_sudha_open_recv_issue_close_split import parse_r15_sudha_open_recv_issue_close_split
from extractors.stock_pdf.layouts.r15_marg_item_opstk_pval_psch_sval import parse_marg_item_opstk_pval_psch_sval

TEXT_PARSERS = {
    # --- 15 July RED-cluster parsers (batch 2) ---
    "metro_sales_stock_statement_glyph": parse_metro_sales_stock_statement_glyph,
    "stock_qoh_paired_value": parse_stock_qoh_paired_value,
    "akshar_open_pur_free_total_sale_free_close": parse_akshar_open_pur_free_total_sale_free_close,
    "klm_ss_marapr_positional": parse_r15_klm_stock_sales_marapr_positional,
    "klm_ss_qty_value_dualfree": parse_klm_ss_qty_value_dualfree,
    "r15_monthly_ss_inward_other_closing": parse_r15_monthly_ss_inward_other_closing,
    "klm_pcode_opstk_psch_ssch_positional": parse_klm_pcode_opstk_psch_ssch_positional,
    "r15_jayambe_monthly_ss_balance": parse_jayambe_monthly_ss_balance,
    "r15_klm_lab_open_recv_sales_close_value_positional": parse_r15_klm_lab_open_recv_sales_close_value_positional,
    "klm_ss_month_totalstock_ilast_positional": parse_r15_klm_ss_month_totalstock_ilast_positional,
    "r15_klm_ss_register_receipt_inst_gr_positional": parse_r15_klm_ss_register_receipt_inst_gr_positional,
    "r15_klm_ss_prevlast_twopage_positional": parse_r15_klm_ss_prevlast_twopage_positional,
    "nu_srishyam_sales_stock_detail": parse_r15_nu_srishyam_sales_stock_detail_tripage,
    "r15_klm_pharmaasia_code_open_recv_sales_close_dualvalue": parse_r15_klm_pharmaasia_code_open_recv_sales_close_dualvalue,
    "r15_pharma_asia_simpleformat": parse_r15_pharma_asia_simpleformat,
    "smartpharma_reps_ostk_replace": parse_smartpharma_reps_ostk_replace,
    "klm_smartpharma_stocksale_tstock": parse_klm_smartpharma_stocksale_tstock,
    "medica_stock_apr_mar": parse_medica_stock_apr_mar,
    "medivision_stock_sales_addless": parse_r15_medivision_stock_sales_addless,
    "klm_ss_combined_pipe_flat": parse_klm_ss_combined_pipe_flat,
    "prompt_datewise_pack_free_inst": parse_prompt_datewise_pack_free_inst,
    "sudha_open_recv_issue_close_split": parse_r15_sudha_open_recv_issue_close_split,
    "marg_item_opstk_pval_psch_sval": parse_marg_item_opstk_pval_psch_sval,
    "klm_lmsale_receipts_age": parse_klm_lmsale_receipts_age,
    "klm_stock_sales_inout_expiry": parse_klm_stock_sales_inout_expiry,
    "stock_unit_op_purc_sale_cl": parse_stock_unit_op_purc_sale_cl,
    "stock_sale_stmt_stkad": parse_stock_sale_stmt_stkad,
    "stock_opbal_issue_expiry_near": parse_stock_opbal_issue_expiry_near,
    "stock_item_desc_oric_movement": parse_stock_item_desc_oric_movement,
    "medivision_company_stock_sales": parse_medivision_company_stock_sales,
    "prompt_datewise_amount_cols": parse_prompt_datewise_amount_cols,
    "marg_stock_ava_bval_sval": parse_marg_stock_ava_bval_sval,
    "marg_sales_stock_statement": parse_marg_sales_stock_statement,
    "marg_stock_sales_expiry_positional": parse_marg_stock_sales_expiry_positional,
    "stock_sales_statement_adjmt_positional": parse_stock_sales_statement_adjmt_positional,
    "stock_oric_receipt_qtyonly": parse_stock_oric_receipt_qtyonly,
    "klm_stock_sales_analysis_movement": parse_klm_stock_sales_analysis_movement,
    "stock_opbal_free_expiry": parse_stock_opbal_free_expiry,
    "stock_ss_analysis_sret_others": parse_stock_ss_analysis_sret_others,
    "klm_ss_statement_receive_close": parse_klm_ss_statement_receive_close,
    "klm_received_issued": parse_klm_received_issued_stmt,
    "swil_recv_issue_stock": parse_swil_recv_issue_stock,
    "klm_stock_sales_month_tots": parse_klm_stock_sales_month_tots,
    "purani_mfr_stock_sales_pdf": parse_purani_mfr_stock_sales_pdf,
    "klm_stock_sales_month_netstock": parse_klm_stock_sales_month_netstock,
    "klm_stock_sales_month_rcpt": parse_klm_stock_sales_month_rcpt,
    "klm_stock_sales_analysis_pcode": parse_klm_stock_sales_analysis_pcode,
    "klm_stock_sales_small_pdf": parse_klm_stock_sales_small_pdf,
    "medichem_ss_expiry": parse_medichem_ss_expiry,
    "meyon_prevmonth_stock": parse_meyon_prevmonth_stock,
    "smartpharma_sas": parse_smartpharma_sas,
    "csquare_manufacturerwise_stock_sales": parse_csquare_manufacturerwise_stock_sales,
    "stock_lstsl": parse_stock_lstsl,
    "product_wise_stock_sale_profit": parse_product_wise_stock_sale_profit,
    "central_stock_sales": parse_central_stock_sales,
    "medivision_stock_sales": parse_medivision_stock_sales,
    "medtraders_sales_stock_statement": parse_medtraders_sales_stock_statement,
    "stock_qoh_returns": parse_stock_qoh_returns,
    "stock_open_rec_adj_close": parse_stock_open_rec_adj_close,
    "swil_stock_lastpurc": parse_swil_stock_lastpurc,
    "stock_open_purch_miscout": parse_stock_open_purch_miscout,
    "klm_stock_sales_month_repq": parse_klm_stock_sales_month_repq,
    "stock_batchwise_statement": parse_stock_batchwise_statement,
    "klm_closing_stock_report": parse_klm_closing_stock_report,
    "marg_sale_closing_pdf": parse_marg_sale_closing_pdf,
    "klm_stock_sale_prvsa": parse_klm_stock_sale_prvsa,
    "marg_monthly_ss_statement_pdf": parse_marg_monthly_ss_statement_pdf,
"stock_open_rcpts_dualsales_pdf": parse_stock_open_rcpts_dualsales_pdf,
    "klm_stock_sales_month": parse_klm_stock_sales_month,
    "saleable_stock_qf": parse_saleable_stock_qf,
"pharmassist_stock_sale": parse_pharmassist_stock_sale,
    "pharmassist_stock_sale_single": parse_pharmassist_stock_sale_single,
    "stock_sale_closing_pairs": parse_stock_sale_closing_pairs,
    "klm_stock_sales_combined_pdf": parse_klm_stock_sales_combined_pdf,
"prompt_dstk_free_pdf": parse_prompt_dstk_free_pdf,
    "marg_movement_detail_sparse": parse_marg_movement_detail_sparse,
"marg_ss_statement_detailed": parse_marg_ss_statement_detailed,
    "marg_stock_recd_issued": parse_marg_stock_recd_issued,
    "marg_stock_summary": parse_marg_stock_summary,
    "stock_open_pur_sale_free_current": parse_stock_open_pur_sale_free_current,
    "marg_stock_analysis_full": parse_marg_stock_analysis_full,
    "klm_stock_sales_analysis_free": parse_klm_stock_sales_analysis_free,
    "pharmassist_mfac": parse_pharmassist_mfac,
    "klm_venus_opstk_crqty": parse_klm_venus_opstk_crqty,
    "dahod_stock_sale_stmt": parse_dahod_stock_sale_stmt,
    "simple4": parse_simple4,
    "qty_value_total": parse_qty_value_total,
    "value_pairs": parse_value_pairs,
    "marg_stock_long": parse_marg_stock_long,
    "marg_qty_value_wide": parse_marg_qty_value_wide,
    "stock_simple_7col": parse_stock_simple_7col,
    "marg_lms_simple": parse_marg_lms_simple,
    "stock_rate_amount": parse_stock_rate_amount,
    "dahod_marg": parse_dahod_marg,
    "stock_receipt_replace": parse_stock_receipt_replace,
    "pharma_bytes_itemcode": parse_pharma_bytes_itemcode,
    "saurashtra_monthly": parse_saurashtra_monthly,
    "saurashtra_ss_report": parse_saurashtra_ss_report,
    "venus_stock_statement": parse_venus_stock_statement,
    "marg_opstk_statement": parse_marg_opstk_statement,
    "prompt": parse_prompt,
    "prompt_datewise_favourite": parse_prompt_datewise_favourite,
    "pks_data": parse_pks_data,
    "technomax_stock": parse_technomax_stock,
    "kluster_stock": parse_kluster_stock,
    "dolphin_stock": parse_dolphin_stock,
    "toreo_stock": parse_toreo_stock,
    "siva_stock": parse_siva_stock,
    "stock_qoh": parse_stock_qoh,
    "stock_open_pur_sale_amt": parse_stock_open_pur_sale_amt,
    "stock_gdin": parse_stock_gdin,
    "stock_oric_pairs": parse_stock_oric_pairs,
    "disa_opbal_receipt_total_issue": parse_disa_opbal_receipt_total_issue,
    "capital_stock_sale_stmt": parse_capital_stock_sale_stmt,
    "swil_stock_transfer": parse_swil_stock_transfer,
    "swil_stock_company_summary": parse_swil_stock_company_summary,
    "marg_pds_replace": parse_marg_pds_replace,
    "marg_open_pur_free_sale": parse_marg_open_pur_free_sale,
    "marg_movement_detail": parse_marg_movement_detail,
    "saraswati_lstsl": parse_saraswati_lstsl,
    "nagendra_rate_pairs": parse_nagendra_rate_pairs,
    "swastik_particulars": parse_swastik_particulars,
    "marg_opqty": parse_marg_opqty,
    "stock_op_pur_total_sale_close": parse_stock_op_pur_total_sale_close,
    "stock_received_issued": parse_stock_received_issued,
    "stock_in_out_statement": parse_stock_in_out_statement,
    "generic": parse_generic,
}

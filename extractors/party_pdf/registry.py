from extractors.party_pdf.layouts.busy_tally import (
    parse_busy_tally,
    parse_busy_tally_itemwise,
)
from extractors.party_pdf.layouts.custom_pharma import parse_custom_pharma
from extractors.party_pdf.layouts.logic_erp import parse_logic_erp
from extractors.party_pdf.layouts.partywise_sales_summary import parse_partywise_sales_summary
from extractors.party_pdf.layouts.customer_invoice_itemwise_sale import parse_customer_invoice_itemwise_sale
from extractors.party_pdf.layouts.marg_bordered import parse_marg_bordered
from extractors.party_pdf.layouts.marg_bordered_billwise import (
    parse_marg_bordered_billwise,
)
from extractors.party_pdf.layouts.marg_register import parse_marg_register
from extractors.party_pdf.layouts.marg_register_itemwise import (
    parse_marg_register_itemwise,
)
from extractors.party_pdf.layouts.marg_sale_details import parse_marg_sale_details
from extractors.party_pdf.layouts.marg_summary import parse_marg_summary
from extractors.party_pdf.layouts.area_item_summary import parse_area_item_summary
from extractors.party_pdf.layouts.profitmaker import parse_profitmaker
from extractors.party_pdf.layouts.sale_register import parse_sale_register_consolidated
from extractors.party_pdf.layouts.manufacturerwise_billwise import parse_manufacturerwise_billwise
from extractors.party_pdf.layouts.customerwise_productwise import parse_customerwise_productwise
from extractors.party_pdf.layouts.billwise_multiheader import parse_billwise
from extractors.party_pdf.layouts.customer_product_grouped import parse_simple_party_itemwise
from extractors.party_pdf.layouts.company_party_summary import parse_company_party_summary
from extractors.party_pdf.layouts.pipe_delimited import parse_pipe_delimited
from extractors.party_pdf.layouts.party_item_summary_nofree import parse_party_item_wise_summary
from extractors.party_pdf.layouts.companywise_customerwise import parse_companywise_customerwise
from extractors.party_pdf.layouts.party_discount_summary import parse_party_discount_summary
from extractors.party_pdf.layouts.saraswati_freeissue import parse_saraswati_freeissue
from extractors.party_pdf.layouts.laxmi_mfac import parse_laxmi_mfac
from extractors.party_pdf.layouts.shree_nath_billwise import parse_shree_nath_billwise
from extractors.party_pdf.layouts.rp_pharma_itemwise import parse_rp_pharma_itemwise
from extractors.party_pdf.layouts.companywise_areawise import parse_companywise_areawise
from extractors.party_pdf.layouts.navkar_productwise import parse_navkar_productwise
from extractors.party_pdf.layouts.bajaj_salestatement import parse_bajaj_salestatement
from extractors.party_pdf.layouts.prathna_register import parse_prathna_register
from extractors.party_pdf.layouts.bharat_saleregister import parse_bharat_saleregister
from extractors.party_pdf.layouts.tax_invoice import parse_tax_invoice
from extractors.party_pdf.layouts.product_party_wise_list import parse_product_party_wise_list
from extractors.party_pdf.layouts.product_itemwise_partywise import parse_product_itemwise_partywise
from extractors.party_pdf.layouts.customer_itemwise_series import parse_customer_itemwise_series
from extractors.party_pdf.layouts.prompt import parse_prompt_free_qty, parse_prompt_normal
from extractors.party_pdf.layouts.technomax import parse_technomax_free_qty
from extractors.party_pdf.layouts.unisolve import parse_unisolve
from extractors.party_pdf.layouts.wep_legacy import parse_wep_legacy

from extractors.party_pdf.layouts.klm_customer_company_product import parse_klm_customer_company_product
from extractors.party_pdf.layouts.klm_customer_vs_item import parse_klm_customer_vs_item
from extractors.party_pdf.layouts.klm_customer_vs_item_summary import parse_klm_customer_vs_item_summary
from extractors.party_pdf.layouts.areawise_partywise_summary_pdf import parse_areawise_partywise_summary_pdf
from extractors.party_pdf.layouts.product_wise_sale_combined import parse_product_wise_sale_combined
from extractors.party_pdf.layouts.marg_sales_analysis_pdf import parse_marg_sales_analysis_pdf
from extractors.party_pdf.layouts.party_product_net_sales_pdf import parse_party_product_net_sales_pdf
from extractors.party_pdf.layouts.jawahar_itemwise_billwise import parse_jawahar_itemwise_billwise

from extractors.party_pdf.layouts.area_item_sales_summary import parse_area_item_sales_summary
from extractors.party_pdf.layouts.medivision_sale_dc import parse_medivision_sale_dc

from extractors.party_pdf.layouts.klm_company_customer_invoice import parse_klm_company_customer_invoice
from extractors.party_pdf.layouts.areawise_sales_billwise import parse_areawise_sales_billwise
from extractors.party_pdf.layouts.customer_product_sales import parse_customer_product_sales
from extractors.party_pdf.layouts.klm_party_wise_statement import parse_klm_party_wise_statement
from extractors.party_pdf.layouts.party_item_summary_sr_total import parse_party_item_summary_sr_total
from extractors.party_pdf.layouts.areawise_sales_statement import parse_areawise_sales_statement
from extractors.party_pdf.layouts.product_customer_wise_sales import parse_product_customer_wise_sales
from extractors.party_pdf.layouts.bluefox_customerwise_sales import parse_bluefox_customerwise_sales
from extractors.party_pdf.layouts.customer_product_wise_summary import parse_customer_product_wise_summary
from extractors.party_pdf.layouts.sale_register_detailed import parse_sale_register_detailed
from extractors.party_pdf.layouts.areawise_sales_period import parse_areawise_sales_period

from extractors.party_pdf.layouts.shivasakthi_areawise_billwise import parse_shivasakthi_areawise_billwise
from extractors.party_pdf.layouts.vasan_areawise_billwise import parse_vasan_areawise_billwise
from extractors.party_pdf.layouts.backbone_mfr_sales_detail import parse_backbone_mfr_sales_detail
from extractors.party_pdf.layouts.klm_group_vs_customer import parse_klm_group_vs_customer
from extractors.party_pdf.layouts.customer_item_wise_sale import parse_customer_item_wise_sale
from extractors.party_pdf.layouts.kapoor_party_itemwise_sale import parse_kapoor_party_itemwise_sale
from extractors.party_pdf.layouts.smartpharma_customer_company_sales import parse_smartpharma_customer_company_sales
from extractors.party_pdf.layouts.marg_sale_summary_party import parse_marg_sale_summary_party
from extractors.party_pdf.layouts.areawise_sales_statement_packing import parse_areawise_sales_statement_packing
from extractors.party_pdf.layouts.prompt_billwise_mixed import parse_prompt_billwise_mixed
from extractors.party_pdf.layouts.sales_statement_summary_itemwise import parse_sales_statement_summary_itemwise
from extractors.party_pdf.layouts.mfacwise_custwise_itemwise import parse_mfacwise_custwise_itemwise
from extractors.party_pdf.layouts.prodcust_wise_billwise import parse_prodcust_wise_billwise, parse_areaprod_wise_billwise
from extractors.party_pdf.layouts.customer_product_wise_packing import parse_customer_product_wise_packing
from extractors.party_pdf.layouts.party_item_summary_qtyfree import parse_party_item_summary_qtyfree
from extractors.party_pdf.layouts.areawise_sales_statement_banded import parse_areawise_sales_statement_banded
from extractors.party_pdf.layouts.company_party_product_sale import parse_company_party_product_sale
from extractors.party_pdf.layouts.party_sale_report import parse_party_sale_report
from extractors.party_pdf.layouts.customerwise_billwise_itemwise import parse_customerwise_billwise_itemwise
from extractors.party_pdf.layouts.party_product_analysis_orion import parse_party_product_analysis_orion

from extractors.party_pdf.layouts.klm_sales_detail_register import parse_klm_sales_detail_register
from extractors.party_pdf.layouts.customer_product_analysis_dash import parse_customer_product_analysis_dash
from extractors.party_pdf.layouts.product_party_wise_freeamt import parse_product_party_wise_freeamt

PARSERS = {
    "klm_sales_detail_register": parse_klm_sales_detail_register,
    "customer_product_analysis_dash": parse_customer_product_analysis_dash,
    "product_party_wise_freeamt": parse_product_party_wise_freeamt,
    "company_party_product_sale": parse_company_party_product_sale,
    "party_sale_report": parse_party_sale_report,
    "customerwise_billwise_itemwise": parse_customerwise_billwise_itemwise,
    "metro_orion_product_analysis": parse_party_product_analysis_orion,
    "partywise_sales_summary": parse_partywise_sales_summary,
    "customer_invoice_itemwise_sale": parse_customer_invoice_itemwise_sale,
    "sales_statement_summary_itemwise": parse_sales_statement_summary_itemwise,
    "mfacwise_custwise_itemwise": parse_mfacwise_custwise_itemwise,
    "prodcust_wise_billwise": parse_prodcust_wise_billwise,
    "areaprod_wise_billwise": parse_areaprod_wise_billwise,
    "customer_product_wise_packing": parse_customer_product_wise_packing,
    "party_item_summary_qtyfree": parse_party_item_summary_qtyfree,
    "areawise_sales_statement_banded": parse_areawise_sales_statement_banded,
    "areawise_sales_statement_packing": parse_areawise_sales_statement_packing,
    "prompt_billwise_mixed": parse_prompt_billwise_mixed,
    "shivasakthi_areawise_billwise": parse_shivasakthi_areawise_billwise,
    "vasan_areawise_billwise": parse_vasan_areawise_billwise,
    "backbone_mfr_sales_detail": parse_backbone_mfr_sales_detail,
    "klm_group_vs_customer": parse_klm_group_vs_customer,
    "customer_item_wise_sale": parse_customer_item_wise_sale,
    "kapoor_party_itemwise_sale": parse_kapoor_party_itemwise_sale,
    "smartpharma_customer_company_sales": parse_smartpharma_customer_company_sales,
    "marg_sale_summary_party": parse_marg_sale_summary_party,
    "sale_register_detailed": parse_sale_register_detailed,
    "areawise_sales_period": parse_areawise_sales_period,
    "customer_product_wise_summary": parse_customer_product_wise_summary,
    "bluefox_customerwise_sales": parse_bluefox_customerwise_sales,
    "product_customer_wise_sales": parse_product_customer_wise_sales,
    "medivision_sale_dc": parse_medivision_sale_dc,
    "area_item_sales_summary": parse_area_item_sales_summary,
    "klm_company_customer_invoice": parse_klm_company_customer_invoice,
    "areawise_sales_billwise": parse_areawise_sales_billwise,
    "customer_product_sales": parse_customer_product_sales,
    "klm_party_wise_statement": parse_klm_party_wise_statement,
    "party_item_summary_sr_total": parse_party_item_summary_sr_total,
    "areawise_sales_statement": parse_areawise_sales_statement,
    "klm_customer_company_product": parse_klm_customer_company_product,
    "klm_customer_vs_item": parse_klm_customer_vs_item,
    "klm_customer_vs_item_summary": parse_klm_customer_vs_item_summary,
    "areawise_partywise_summary_pdf": parse_areawise_partywise_summary_pdf,
    "product_wise_sale_combined": parse_product_wise_sale_combined,
    "marg_sales_analysis_pdf": parse_marg_sales_analysis_pdf,
    "party_product_net_sales_pdf": parse_party_product_net_sales_pdf,
    "jawahar_itemwise_billwise": parse_jawahar_itemwise_billwise,
    "marg_summary": parse_marg_summary,
    "marg_register": parse_marg_register,
    "marg_register_itemwise": parse_marg_register_itemwise,
    "marg_sale_details": parse_marg_sale_details,
    "marg_bordered": parse_marg_bordered,
    "marg_bordered_billwise": parse_marg_bordered_billwise,
    "unisolve": parse_unisolve,
    "busy_tally": parse_busy_tally,
    "busy_tally_itemwise": parse_busy_tally_itemwise,
    "logic_erp": parse_logic_erp,
    "wep_legacy": parse_wep_legacy,
    "custom_pharma": parse_custom_pharma,
    "profitmaker": parse_profitmaker,
    "sale_register_consolidated": parse_sale_register_consolidated,
    "area_item_summary": parse_area_item_summary,
    "manufacturerwise_billwise": parse_manufacturerwise_billwise,
    "customerwise_productwise": parse_customerwise_productwise,
    "billwise_multiheader": parse_billwise,
    "customer_product_grouped": parse_simple_party_itemwise,
    "company_party_summary": parse_company_party_summary,
    "pipe_delimited": parse_pipe_delimited,
    "party_item_summary_nofree": parse_party_item_wise_summary,
    "companywise_customerwise": parse_companywise_customerwise,
    "party_discount_summary": parse_party_discount_summary,
    "saraswati_freeissue": parse_saraswati_freeissue,
    "laxmi_mfac": parse_laxmi_mfac,
    "shree_nath_billwise": parse_shree_nath_billwise,
    "rp_pharma_itemwise": parse_rp_pharma_itemwise,
    "companywise_areawise": parse_companywise_areawise,
    "navkar_productwise": parse_navkar_productwise,
    "bajaj_salestatement": parse_bajaj_salestatement,
    "prathna_register": parse_prathna_register,
    "bharat_saleregister": parse_bharat_saleregister,
    "tax_invoice": parse_tax_invoice,
    "product_party_wise_list": parse_product_party_wise_list,
    "product_itemwise_partywise": parse_product_itemwise_partywise,
    "customer_itemwise_series": parse_customer_itemwise_series,
    "prompt_normal": parse_prompt_normal,
    "prompt_free_qty": parse_prompt_free_qty,
    "technomax_free_qty": parse_technomax_free_qty,
}

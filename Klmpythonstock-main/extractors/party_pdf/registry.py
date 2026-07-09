from extractors.party_pdf.layouts.busy_tally import (
    parse_busy_tally,
    parse_busy_tally_itemwise,
)
from extractors.party_pdf.layouts.custom_pharma import parse_custom_pharma
from extractors.party_pdf.layouts.logic_erp import parse_logic_erp
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

PARSERS = {
    "medivision_sale_dc": parse_medivision_sale_dc,
    "area_item_sales_summary": parse_area_item_sales_summary,
    "klm_company_customer_invoice": parse_klm_company_customer_invoice,
    "areawise_sales_billwise": parse_areawise_sales_billwise,
    "customer_product_sales": parse_customer_product_sales,
    "klm_party_wise_statement": parse_klm_party_wise_statement,
    "party_item_summary_sr_total": parse_party_item_summary_sr_total,
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

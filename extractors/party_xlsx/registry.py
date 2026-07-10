from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.layouts.area_item_sales_summary import parse_area_item_sales_summary
from extractors.party_xlsx.layouts.item_item_sales_summary import parse_item_item_sales_summary
from extractors.party_xlsx.layouts.item_item_sales_summary_text import parse_item_item_sales_summary_text
from extractors.party_xlsx.layouts.area_party_billwise import parse_area_party_billwise
from extractors.party_xlsx.layouts.company_area_wise_sales import parse_company_area_wise_sales
from extractors.party_xlsx.layouts.product_customer_wise_sales_xlsx import parse_product_customer_wise_sales_xlsx
from extractors.party_xlsx.layouts.companywise_customerwise import parse_companywise_customerwise
from extractors.party_xlsx.layouts.customer_company_itemwise import parse_customer_company_itemwise
from extractors.party_xlsx.layouts.customer_product_banded import parse_customer_product_banded
from extractors.party_xlsx.layouts.customer_product_wise_band import parse_customer_product_wise_band
from extractors.party_xlsx.layouts.data_spec_sale_by_item import parse_data_spec_sale_by_item
from extractors.party_xlsx.layouts.fawin_partywise import parse_fawin_partywise
from extractors.party_xlsx.layouts.infosoft_bandwise import parse_infosoft_bandwise
from extractors.party_xlsx.layouts.itemwise_party_column import parse_itemwise_party_column
from extractors.party_xlsx.layouts.jaimini_partywise import parse_jaimini_partywise
from extractors.party_xlsx.layouts.marg_busy import parse_marg_busy
from extractors.party_xlsx.layouts.marg_register_excel import parse_marg_register_excel
from extractors.party_xlsx.layouts.painkiller_partywise import parse_painkiller_partywise
from extractors.party_xlsx.layouts.party_item_summary import parse_party_item_summary
from extractors.party_xlsx.layouts.party_item_wise_sale import parse_party_item_wise_sale
from extractors.party_xlsx.layouts.partywise_band import parse_partywise_band
from extractors.party_xlsx.layouts.product_name_city import parse_product_name_city
from extractors.party_xlsx.layouts.product_party_banded import parse_product_party_banded
from extractors.party_xlsx.layouts.salesmen_partywise import parse_salesmen_partywise
from extractors.party_xlsx.layouts.tabular import records_from_mapped
from extractors.party_xlsx.layouts.tabular_party_product import parse_tabular_party_product

from extractors.party_xlsx.layouts.areawise_partywise_summary_xlsx import parse_areawise_partywise_summary_xlsx
from extractors.party_xlsx.layouts.marg_sales_analysis_xlsx import parse_marg_sales_analysis_xlsx
from extractors.party_xlsx.layouts.party_product_net_sales_xlsx import parse_party_product_net_sales_xlsx

from extractors.party_xlsx.layouts.product_areawise_pivot import parse_product_areawise_pivot

from extractors.party_xlsx.layouts.customer_items_new_xlsx import parse_customer_items_new_xlsx
from extractors.party_xlsx.layouts.company_customer_itemwise_banded import parse_company_customer_itemwise_banded
from extractors.party_xlsx.layouts.company_party_product_xlsx import parse_company_party_product_xlsx

PARSERS = {
    "company_party_product_xlsx": parse_company_party_product_xlsx,
    "customer_items_new_xlsx": parse_customer_items_new_xlsx,
    "company_customer_itemwise_banded": parse_company_customer_itemwise_banded,
    "area_item_sales_summary": parse_area_item_sales_summary,
    "item_item_sales_summary": parse_item_item_sales_summary,
    "item_item_sales_summary_text": parse_item_item_sales_summary_text,
    "product_areawise_pivot": parse_product_areawise_pivot,
    "areawise_partywise_summary_xlsx": parse_areawise_partywise_summary_xlsx,
    "marg_sales_analysis_xlsx": parse_marg_sales_analysis_xlsx,
    "party_product_net_sales_xlsx": parse_party_product_net_sales_xlsx,
    "tabular_party_product": parse_tabular_party_product,
    "marg_busy": parse_marg_busy,
    "marg_register_excel": parse_marg_register_excel,
    "infosoft_bandwise": parse_infosoft_bandwise,
    "jaimini_partywise": parse_jaimini_partywise,
    "painkiller_partywise": parse_painkiller_partywise,
    "data_spec_sale_by_item": parse_data_spec_sale_by_item,
    "fawin_partywise": parse_fawin_partywise,
    "itemwise_party_column": parse_itemwise_party_column,
    "customer_product_banded": parse_customer_product_banded,
    "customer_company_itemwise": parse_customer_company_itemwise,
    "party_item_wise_sale": parse_party_item_wise_sale,
    "partywise_band": parse_partywise_band,
    "area_party_billwise": parse_area_party_billwise,
    "company_area_wise_sales": parse_company_area_wise_sales,
    "product_customer_wise_sales_xlsx": parse_product_customer_wise_sales_xlsx,
    "companywise_customerwise": parse_companywise_customerwise,
    "salesmen_partywise": parse_salesmen_partywise,
    "party_item_summary": parse_party_item_summary,
    "product_name_city": parse_product_name_city,
    "product_party_banded": parse_product_party_banded,
    "customer_product_wise_band": parse_customer_product_wise_band,
}


def parse_rows(rows, layout):
    if layout in PARSERS:
        return PARSERS[layout](rows)
    header_idx = detect_header_row(rows)
    if header_idx is not None:
        headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[header_idx])]
        return records_from_mapped(headers, rows, header_idx)
    return [], {}

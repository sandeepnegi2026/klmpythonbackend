import re


def detect_format(text, n_rects, n_lines):
    t = text[:2000]
    tl = t.lower()
    tl_compact = re.sub(r"\s+", "", tl)
    # SIND DISTRIBUTORS "MediVision Platinum" customer-wise/product-wise sale-DC.
    # Adobe-UTF-8 CID font — pdfminer yields nothing; pdf_io falls back to PyMuPDF
    # and this positional parser reads word x-coords via fitz. Title signature is
    # unique across all New_Data PDFs (zero collisions).
    if "customer-wise,product-wisesale/dcdetails" in tl_compact:
        return "medivision_sale_dc"
    if "freequantitystatement" in tl_compact:
        return "technomax_free_qty"
    if "customer & product analysis" in tl:
        return "profitmaker"
    if "partynameitemnamequantityfreeamount" in tl_compact:
        return "sale_register_consolidated"
    # KHATTAR "SALE REGISTER CONSOLIDATED" variant with an extra AVG.RATE column
    # (PARTY NAME ITEM NAME QUANTITY FREE AVG.RATE AMOUNT -> 4 numbers/row).
    if "partynameitemnamequantityfreeavg.rateamount" in tl_compact:
        return "sale_register_consolidated"
    # SwilERP "Product-Customer Wise Sales" (CAPITAL PHARMA AGENCIES): product
    # bands with per-customer rows (Customer | Station | Qty | Sales Value).
    # Positional — word x0 slices the columns the flat text can't.
    if (
        "product-customerwisesales" in tl_compact
        and "customerstationqty.salesvalue" in tl_compact
    ):
        return "product_customer_wise_sales"
    # AGARTALA PHARMA "AREA / ITEM WISE SALES SUMMARY": party bands prefixed with '-', header
    # DESCRIPTION QTY. FREE RATE AMOUNT. The 5S PHARMA area_item_summary variant carries an
    # extra '( % )' discount column, so the paren-guard keeps those on area_item_summary below.
    if (
        "area/itemwisesalessummary" in tl_compact
        and "descriptionqty.freerateamount" in tl_compact
        and "descriptionqty.freerateamount(" not in tl_compact
    ):
        return "area_item_sales_summary"
    if "d e s c r i p t i o n" in tl and re.search(r"area\s*/\s*item\s*wise", tl):
        return "area_item_summary"
    if "sales detail register" in tl and (
        "itemwise-customerwise" in tl or "mf-itemwise" in tl
    ):
        return "marg_register_itemwise"
    if "sales detail summary" in tl and (
        "mf-customer" in tl or "mf - customer" in tl
    ):
        return "marg_summary"
    if "sales detail register" in tl and "mf-customer" in tl:
        return "marg_register"
    if "sale details" in tl and n_lines > 5:
        return "marg_sale_details"
    if n_rects > 50 and re.search(r"from:\s*\d{2}/\d{2}", tl):
        return "marg_bordered_billwise" if "bill no" in tl else "marg_bordered"
    # MAHESH "Customer-Wise Product-Wise Sales Summary": coded customer bands
    # ("A004 <NAME>,<CITY>") with per-product AGGREGATE rows (no bill numbers) —
    # the Unisolve billwise parser 0-rows it. Gate on its unique compact column
    # header; must precede the broader unisolve title rule below.
    if "codecustomername&cityprd.codeproductname" in tl_compact:
        return "customer_product_wise_summary"
    if "customer-wise product-wise" in tl and "----" in t:
        return "unisolve"
    if "item / item wise" in tl or "item/item wise" in tl:
        return "busy_tally_itemwise"
    # YUVEE 3-band "PARTY / ITEM WISE SALES SUMMARY" (SALE / SALES RETURN / TOTAL with an
    # AVR.RATE column, 12 numbers per row) — busy_tally's per-line 5/6-number patterns reject
    # its rows (0 extracted). The AVR.RATE column exists ONLY in this summary; corpus-wide the
    # 282 busy_tally files carry the same title but none carry 'avr.rate'. MUST precede busy_tally.
    if "party/itemwisesalessummary" in tl_compact and "avr.rate" in tl_compact:
        return "party_item_summary_sr_total"
    # AMRITA "PARTY / ITEM WISE SALES SUMMARY" QTY+FREE-only variant (header
    # 'D E S C R I P T I O N QTY. FREE' — NO rate/amount/value column). Both
    # party_item_summary_nofree (needs money tokens) and busy_tally 0-row it.
    # The 'freerateamount' exclusion protects the area_item_sales_summary sibling
    # (its header contains 'descriptionqty.free' as a substring). MUST precede busy_tally.
    if (
        "party/itemwisesalessummary" in tl_compact
        and "descriptionqty.free" in tl_compact
        and "descriptionqty.freerateamount" not in tl_compact
        and "avr.rate" not in tl_compact
    ):
        return "party_item_summary_qtyfree"
    if "party / item wise" in tl or "party/item" in tl:
        return "busy_tally"
    if (
        "customer / company / itemwise" in tl
        and "codeitemnamepackingbatchno.qty.fqty" in tl_compact
    ):
        # Series-banded variant (no Sr column, integer qty, dd/mm/yyyy dates,
        # VC/AC##### invoices). The Sr.-column variant still routes to logic_erp.
        return "customer_itemwise_series"
    if "customer / company / itemwise" in tl:
        return "logic_erp"
    if "product c" in tl and "====" in t:
        return "wep_legacy"
    if n_rects > 5 and re.search(r"from:\s*\d{2}/\d{2}", tl):
        return "marg_bordered"
    if (
        re.search(r"free\s+quantity", tl)
        and "billref" in tl_compact
        and "statement" not in tl_compact
    ):
        return "prompt_free_qty"
    # Prompt ERP "Normal" party-billwise, mixed-case BillRef variant (SHRI ASHOK
    # "klm party"). Same header/structure as prompt_normal but BillRefs are Cash/1130,
    # Credit-L/196, Credit-O/261 (mixed/lower-case), which prompt_normal's uppercase-only
    # regex 0-rows. Gated on the mixed-case token; MUST precede the prompt_normal rule.
    if (
        "productpackbillrefdatemrpbatchqtyfreerateamount" in tl_compact
        and (re.search(r"cash/\d", tl) or "credit-" in tl)
    ):
        return "prompt_billwise_mixed"
    if re.search(r"(normal|party)\s+from:", tl) and (
        "billref" in tl_compact or "bill ref" in tl
    ):
        return "prompt_normal"
    # --- New KLM party layouts (placed last so existing rules always win; these
    #     only catch files that otherwise fall through to "unknown"). Header
    #     signatures are matched over the FULL text since a column header can sit
    #     below the first 2000 chars on long reports. Each signal is verified to
    #     match only its own files (no already-working file is rerouted).
    tfull = text.lower()
    cfull = re.sub(r"\s+", "", tfull)
    if "manufacturerwise sales report" in tfull and "billdatebillnoproductname" in cfull:
        return "manufacturerwise_billwise"
    if "customerwise-productwise" in cfull and "lifecareformulations" in cfull:
        return "customerwise_productwise"
    if (
        "productnamepackingbillnobl.dateqtyf.qtyrateamount" in cfull
        or "billno.billproductnamepackingbatchqtyfreeratevalue" in cfull
        or "datetrn.no.codeitemnameqty.freeratevalue" in cfull
        or "namepackbillrefdatemrpbatchqtyfreerateamount" in cfull
    ):
        return "billwise_multiheader"
    if (
        ("productpartyanalysis" in cfull and "codepartynameareaqtyfreeamount" in cfull)
        or ("company-customer-itemwisesale" in cfull)
        or ("customer-itemwisesale" in cfull and "itemnamepackqty" in cfull)
        or ("customer-productwisesales" in cfull and "productcodeproductnamepacking" in cfull)
    ):
        return "customer_product_grouped"
    if "company/partywisesalessummary" in cfull and "sno.descriptionsalesreturnamount" in cfull:
        return "company_party_summary"
    if (
        ("srno|entryno" in cfull and "accountname" in cfull)
        or ("product|hsn|pkg" in cfull and "|amount|" in cfull)
    ):
        return "pipe_delimited"
    if (
        "d e s c r i p t i o n" in tfull
        and "party/itemwisesalessummary" in cfull
        and "descriptionqty.rateamount" in cfull
        and "areaitemwise" not in cfull
    ):
        return "party_item_summary_nofree"
    # --- Tail layouts from the second workflow sweep (each verified to match only
    #     its own currently-"unknown" file; placed last so existing rules win). ---
    if "companywisecustomerwisereport" in cfull:
        return "companywise_customerwise"
    if "partydiscountsummaryonsales" in cfull:
        return "party_discount_summary"
    if "product-wisecustomer-wisefreeissue" in cfull:
        return "saraswati_freeissue"
    if "mfac group wise report" in tfull:
        return "laxmi_mfac"
    if "billnodateproductnam" in cfull and "qty.fr.sch.qty" in cfull:
        return "shree_nath_billwise"
    if "itemwise sales details" in tfull and "party code & name" in tfull:
        return "rp_pharma_itemwise"
    if "companywiseareawisesalesdetail" in cfull:
        return "companywise_areawise"
    if "datebillnoproducthsnpack" in cfull:
        return "navkar_productwise"
    if "salesstatement" in cfull and "partynameamountdiscountnetamt" in cfull:
        return "bajaj_salestatement"
    if "billdatepartynameitemnametotalpacks" in cfull:
        return "bharat_saleregister"
    if "tobuyername" in cfull and "ratedisc%gst%amount" in cfull:
        return "tax_invoice"
    if "product + party wise list" in tfull:
        return "product_party_wise_list"
    if "a.qtyfr.qtytotalqty" in cfull:
        return "product_itemwise_partywise"
    if (
        "customer,companyandproductsales" in cfull
        and "productnamepackingqtyfreerateamount" in cfull
    ):
        return "klm_customer_company_product"
    # SRI VASAVI DOSPrinter "COMPANY, CUSTOMER AND INVOICE SALES": Customer:<name>,<town>
    # bands + invoice-level rows (Inv|Date|Product|Pack|Batch|Qty|Free|Price|Value|Discount).
    # Distinct from klm_customer_company_product above (different word order, no Invoice/Batch/
    # Discount columns). Placed after it so existing rules always win.
    if (
        "company,customerandinvoicesales" in cfull
        and "invoiceinvoiceproductnamepackingbatchquantityfreepricevaluediscount" in cfull
    ):
        return "klm_company_customer_invoice"
    # SmartPharma360 "Customer-Company wise Product Sales" (KLM): Company Name: bands ->
    # per-invoice rows (Inv.No|InvDate|Product Name|Batch|Qty|Free|Rate|Value). Distinct
    # header from the klm_company_customer_invoice sibling above. Tail-placed.
    if (
        "customer-companywiseproductsales" in cfull
        and "inv.no.invdateproductnamebatchqtyfreeratevalue" in cfull
    ):
        return "smartpharma_customer_company_sales"
    # SRI SHIRIDI SAI "Group Vs Customer Details" (KLM): product item-line + number-line
    # merged per row, customer-code paren bands. Distinct from klm_customer_vs_item below
    # (which needs 'customervsitemdetails'); tokens unique. Tail-placed.
    if (
        "groupvscustomerdetails" in cfull
        and "towndatenumberbatchmrpqtyfreereplacerategrossvaluenetvalue" in cfull
    ):
        return "klm_group_vs_customer"
    if (
        "customervsitemdetails" in cfull
        and "itemnameitemtownbilldatebillno" in cfull
    ):
        return "klm_customer_vs_item"
    if "customervsitemsummaries" in cfull and "group/names.qtys.free" in cfull:
        return "klm_customer_vs_item_summary"
    if "areawisepartywisesalessummary" in cfull and "productnamepackmakemaytotal" in cfull:
        return "areawise_partywise_summary_pdf"
    if "productwisesalelist(combined)" in cfull:
        return "product_wise_sale_combined"
    if (
        "salesanalysis" in cfull
        and "itemqtyfreevalue#totalqtytotalfreetotalvalue" in cfull
    ):
        # Marg "Sales Analysis" party report (VENUS PHARMA / KLM). 3-level banded
        # (Manufacturer -> Customer -> item lines) with a two-column glyph-bled
        # PDF text layer, so it is parsed positionally by word x-coordinates.
        # Signature = the full compact column header, verified to match ONLY this
        # file across the whole corpus (1/186 New_Data PDFs).
        return "marg_sales_analysis_pdf"
    if (
        "party/productwisenetsales" in cfull
        and "party/productnamesaleqtyretqtynetqty" in cfull
    ):
        return "party_product_net_sales_pdf"
    if (
        "billno.datenameofcustomerplacebatchqtyfreevalue" in cfull
        and "itemwise-billwise" in tfull
    ):
        return "jawahar_itemwise_billwise"
    # JEYANTHI PHARMAA "Areawise Sales Report" (KLM billwise, monospace DOS export): AREA
    # bands -> customer blocks -> bill-line item rows, free/scheme qty in the 'Repl' column.
    # Appended at the very tail so only files that fall through EVERY existing rule (currently
    # 'unknown', 0 rows) can reach it — no working file can be rerouted.
    if (
        "areawisesalesreport" in cfull
        and "productnamecustomernamebillnumberbilldatpackquanfreereplsalesvalue" in cfull
    ):
        return "areawise_sales_billwise"
    # SHREE SHIVASAKTHI MEDICAL AGENCIES "Areawise Sales Report" (KLM billwise,
    # monospace DOS export): CUSTOMER bands -> bill/item rows -> Customer Sub
    # Total + bare-7-num roll-up echoes. Different column order from JEYANTHI
    # (bill-first with customer BAND vs product-first with customer COLUMN), so
    # its header token is unique. Tail-placed so every existing rule wins first.
    if (
        "areawisesalesreport" in cfull
        and "billnumberbilldatepproductnamepackingquantfreeqdsalevaluetaxamounetamountrep" in cfull
    ):
        return "shivasakthi_areawise_billwise"
    # VASAN MEDICAL AGENCIES "Areawise Sales Report ... for <DIV> KLM LABORATORIES
    # PVT LTD": PRODUCT-FIRST billwise, AREA/CUSTOMER/TOWN carried in a positional
    # BAND (split by word x0), free/scheme qty in 'Free' col, 'Repl' always '-'.
    # Its column header differs from JEYANTHI's (packi/billnumber/qty/free/repl/
    # saleval) so no overlap. Tail-placed.
    if (
        "areawisesalesreport" in cfull
        and "productnamepackibillnumberbilldateqtyfreereplsaleval" in cfull
    ):
        return "vasan_areawise_billwise"
    # C.D. ASSOCIATES "Customer & Product Sales" (Customer:<name> City:<city> bands, MP#####
    # invoice rows). Tail-placed so every existing rule wins first.
    if "customer&productsales" in cfull and "inv.nodateproductpackbatchqtyfreeratevalue" in cfull:
        return "customer_product_sales"
    # DEEPA(A) "PARTY WISE SALES STATEMENT" (KLM division bands, PARTY NAME ITEM NAME REP FRE
    # QTY VALUE DISC NET AMT; positional). Tail-placed.
    if "partywisesalesstatement" in cfull and "itemnamerepfreqtyvaluediscnetamt" in cfull:
        return "klm_party_wise_statement"
    # CENTRAL AGENCIES "Areawise Sales Statment" (KLM billwise, text/plumber).
    # Signature = its unique compact column header; "codecustomernamerepcode"
    # collides with no other layout. Tail-placed so every existing rule wins.
    # CENTRAL DISTRIBUTORS "Areawise Sales Statment" — Packing-column variant of the
    # CENTRAL AGENCIES areawise_sales_statement: header carries an explicit "Packing"
    # column and the Rep Code is an alphabetic rep *name*, so the numeric-rep
    # areawise_sales_statement parser reads 0 rows. Its header token is a SUPERSET of the
    # plain gate below, so it MUST precede it.
    if "billnobilldatecodecustomernamerepcodeproductnamepackingqtyfreeqty" in cfull:
        return "areawise_sales_statement_packing"
    if "billnobilldatecodecustomernamerepcodeproductname" in cfull:
        return "areawise_sales_statement"
    # CENTRAL AGENCIES "Areawise Sales Statement" — AREA+CUSTOMER banded BlueFox variant
    # (KLM COSMO): NO Code/Customer Name/Rep Code column, so its header reads
    # 'billnobilldateproductname...' (not 'billnobilldatecodecustomername...'). Mutually
    # exclusive with the two gates above; party comes from the comma-bearing customer sub-band.
    if (
        "areawisesalesstatement" in cfull
        and "billnobilldateproductnamepackingqtyfreeqtyamount" in cfull
    ):
        return "areawise_sales_statement_banded"
    # VASAVI MEDICARE "Area Wise Sales Report for the period of <ISO> and
    # <ISO>": "<CODE> - <PARTY>, <AREA>-<PIN>" bands + invoice rows. Signature =
    # title + its compact column header. Tail-placed. (The JEYANTHI
    # areawise_sales_billwise gate needs a DIFFERENT column header, no overlap.)
    if (
        "areawisesalesreportfortheperiodof" in cfull
        and "sr.codeproductnamepackingbatchno.qtyfqtysch" in cfull
    ):
        return "areawise_sales_period"
    # VIJAY MEDICAL "SALE REGISTER DETAILED" (Marg billwise): "PARTY NAME - X"
    # bands, SNO|BILL DATE|BILL NO.|ITEM|LOT|QTY|FREE|RATE/UNIT|NET AMOUNT rows.
    # Signature = title + its compact header run. Tail-placed.
    if (
        "saleregisterdetailed" in cfull
        and "billdatebillno.itemname" in cfull
    ):
        return "sale_register_detailed"
    # BlueFox Systems "Customerwise Sales Statement on <Month>/<Year>" (FATIMA
    # HEALTHCARE): "<PARTY>,<TOWN>" bands -> bill rows. Signature = title + its
    # compact column header (both required). Tail-placed so existing rules win.
    if (
        "customerwisesalesstatementon" in cfull
        and "billdatebillnoproductpackingqtyfreeamount" in cfull
    ):
        return "bluefox_customerwise_sales"
    # PURANI HOSPITAL SUPPLIES "BackBone MFR Sales Detail Report" (11-col lattice):
    # Product|BillNo/Date|Customer|City|Batch|Expiry|Qty|Free|Rpl|PTR|Total Sales.
    # Positional lattice parser + straddle recovery. Tail-placed.
    if (
        "mfrsalesdetailreport" in cfull
        and "productnamebillno/datecustomernamecitybatchexpiryqtyfreeqty" in cfull
    ):
        return "backbone_mfr_sales_detail"
    # RAKESH MEDICAL STORES (Shimla) LOGIC ERP "CUSTOMER+ITEM WISE SALE". Positional;
    # '+' title distinguishes it from the hyphen 'customer-itemwisesale' rule above.
    if "customer+itemwisesale" in cfull and "customernameitemname" in cfull:
        return "customer_item_wise_sale"
    # KAPOOR MEDICAL STORE "PARTY+ITEM WISE SALE" (Marg billwise, positional): PARTY
    # NAME bands -> SNO|BILL NO|BILL DATE|ITEM|QTY|[FREE]|EXPIRY|MRP|GROSS|NET rows.
    if (
        "party+itemwisesale" in cfull
        and "billno.billdateitemname" in cfull
    ):
        return "kapoor_party_itemwise_sale"
    # UNIVERSAL MEDICAL AGENCY Marg "SALE SUMMARY" party-level roll-up (text): one row
    # per party "<PARTY> <int-May> <TotalValue>". Month-agnostic gate; 'salesummary'
    # (single 's') is NOT a substring of company_party_summary's 'salessummary'.
    if "salesummary" in cfull and "totalvalue" in cfull and "netsales" in cfull:
        return "marg_sale_summary_party"
    # KRISHNA SAI "Sales Statement Summary" (KLM division reports). ITEM-primary rows;
    # gated on title + its exact compact ITEM-first column header (distinct from the
    # PARTY-first sale_register 'partynameitemname...').
    if (
        "salesstatementsummary" in cfull
        and "itemnamepartynamequantityfreesaleamounttaxamount" in cfull
    ):
        return "sales_statement_summary_itemwise"
    # BALAJI "Mfacwise Custwise Areawise Itemwise Report" (KLM COSMO). Single unique token.
    if "mfacwisecustwiseareawiseitemwisereport" in cfull:
        return "mfacwise_custwise_itemwise"
    # SREE SUPREME (NAMAKKAL) KLM CASMO DOS exports — two sibling positional billwise
    # reports. Slash/dot tokens are distinct from the hyphenated product/customer gates.
    if "prod/cust.wisesales" in cfull and "inv.noinv.datecustomernameplaceqtyfreereplratevalue" in cfull:
        return "prodcust_wise_billwise"
    if "area-prod-wisesales" in cfull and "productnamepackginv.noinv.dateqtyfreereplvalue" in cfull:
        return "areaprod_wise_billwise"
    # Agrawal "Customer-Product wise Sales": CODE-NAME party headings + product rows
    # 'Product Name Packing Qty. Freeqty Value' (no product-code column, so distinct
    # from customer_product_grouped's 'productcodeproductnamepacking' gate above).
    if "customer-productwisesales" in cfull and "productnamepackingqty.freeqtyvalue" in cfull:
        return "customer_product_wise_packing"
    return "unknown"

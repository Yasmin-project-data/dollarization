# Data sources

## Household deposits by currency
- File: deposits_individuals_nbk.xlsx
- Publisher: National Bank of the Republic of Kazakhstan (NBK)
- URL: https://nationalbank.kz/ru/depositspopulation/vklady-naseleniya-v-bankah-kazahstana
- Navigation path: nationalbank.kz → Statistics → Monetary and banking statistics → Household deposits in banks of Kazakhstan
- Indicators selected: all breakdowns by deposit type and currency (national / foreign); "Total" not selected but included in export
- Period selected on website: 2010-01-01 to 2026-09-30
- Period in file: 2010-01 to 2026-08 (200 monthly observations; September 2026 not yet published)
- Retrieved: 2026-10-04
- Frequency: monthly, end of period
- Units: million KZT
- Date format in file: MM.YY (e.g. 01.10 = January 2010)
- Publication lag: about 1 month
- Format: XLSX, exported manually from the NBK website
- Note: includes non-resident accounts (NBK footnote)
- Note: December 2019 data include final turnovers (NBK footnote)
- Revisions: to be checked

## USD/KZT official exchange rate, daily
- File: usd_kzt_daily_nbk_api.csv
- Publisher: National Bank of the Republic of Kazakhstan (NBK)
- API query: https://nationalbank.kz/rss/get_rates.cfm?fdate=DD.MM.YYYY (one request per calendar day)
- Downloaded by: src/download_rates.py
- Period: 2010-01-01 to 2026-09-30
- Retrieved: 2026-10-04
- Frequency: daily official rate; converted to monthly average and end-of-month in src/ingest.py
- Note: XLSX export on the NBK website returned AUD regardless of currency selected, and the PDF report had unreadable pages, so the official NBK API was used
## Manually transcribed values
- File: manual_values.csv
- Contents: USD/KZT official monthly average for August 2023, transcribed by hand from the NBK file "2023 год" at https://nationalbank.kz/ru/news/oficialnye-kursy
- Reason: daily rates for 2023-07-28 to 2023-08-28 are missing from both the NBK API and the NBK website report; only 4 daily values remain for August 2023
- Retrieved: 2026-10-04